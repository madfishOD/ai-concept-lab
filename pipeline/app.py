from __future__ import annotations
import asyncio, io, json, secrets, time, uuid
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, ImageOps, UnidentifiedImageError
from .core import ROOT, DATA, CONFIG, initialize, library, catalog, resolve_asset, validate_edit, get_job, put_job, jobs
from .services import ComfyClient, plan_with_agent
from .runner import GPU_LOCK, WORK, start_worker

@asynccontextmanager
async def lifespan(app):
    initialize(); start_worker(); yield

app=FastAPI(title='Anima Concept Lab',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')

@app.middleware('http')
async def local_only(request, call_next):
    # Local prototype: prevent foreign webpages sending mutations to localhost.
    origin=request.headers.get('origin')
    if origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765'):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'Only local application origin is allowed'},status_code=403)
    return await call_next(request)

@app.get('/')
def home(): return FileResponse(ROOT/'web/index.html')

@app.get('/api/library')
def get_library(): return library()

@app.get('/api/catalog')
def get_catalog(): return catalog()

@app.get('/api/library/{ref_id}/image')
def reference_image(ref_id:str):
    ref=next((r for r in library() if r['id']==ref_id),None)
    if not ref: raise HTTPException(404,'Референс не знайдено')
    return FileResponse(ROOT/'library'/ref['file'])

@app.get('/api/assets/{asset_id}')
def asset(asset_id:str):
    try: return FileResponse(resolve_asset(asset_id),media_type='image/png')
    except ValueError as error: raise HTTPException(404,str(error))

@app.post('/api/uploads')
async def upload(file:UploadFile=File(...)):
    raw=await file.read(25*1024*1024+1)
    if len(raw)>25*1024*1024: raise HTTPException(413,'Ліміт зображення — 25 MB')
    try:
        with Image.open(io.BytesIO(raw)) as incoming:
            if incoming.format not in ('PNG','JPEG','WEBP'): raise ValueError('Потрібне PNG, JPEG або WebP')
            if incoming.width*incoming.height>32_000_000: raise ValueError('Ліміт — 32 мегапікселі')
            image=ImageOps.exif_transpose(incoming).convert('RGBA' if 'A' in incoming.getbands() else 'RGB')
            asset_id=str(uuid.uuid4()); image.save(DATA/'uploads'/f'{asset_id}.png')
            return {'id':asset_id,'width':image.width,'height':image.height,'name':file.filename}
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError) as error:
        raise HTTPException(400,str(error))

class Brief(BaseModel):
    brief:str=Field(min_length=3,max_length=4000)
    source_id:str|None=None
    mask_id:str|None=None
    reference_ids:list[str]=Field(default_factory=list,max_length=4)

@app.post('/api/plan')
async def create_plan(request:Brief):
    if not GPU_LOCK.acquire(blocking=False): raise HTTPException(409,'Зараз виконується генерація. Планування буде доступне після неї.')
    try:
        valid_ids={r['id'] for r in library()}
        if set(request.reference_ids)-valid_ids: raise ValueError('Невідомий референс')
        source=resolve_asset(request.source_id) if request.source_id else None
        if request.mask_id:
            if not source: raise ValueError('Маска потребує вихідного зображення')
            validate_edit(source,resolve_asset(request.mask_id))
        # Qwen and diffusion share one GPU. Only unload idle ComfyUI weights.
        comfy=ComfyClient()
        try:
            pending=await asyncio.to_thread(comfy.queue)
        except (httpx.RequestError,RuntimeError): pending=None
        if pending:
            if pending.get('queue_running') or pending.get('queue_pending'):
                raise HTTPException(409,'ComfyUI має активну чергу. Дочекайтеся її завершення перед запуском Qwen.')
            await asyncio.to_thread(comfy.request,'POST','/free',json={'unload_models':True,'free_memory':True})
        answer=await asyncio.to_thread(plan_with_agent,request,source)
        if answer.get('workflow_id') not in {'concept_generate','concept_edit_masked','clarify','unsupported'}:
            raise ValueError('Агент повернув невідому операцію')
        if set(answer.get('reference_ids',[]))-valid_ids: raise ValueError('Агент повернув невідомий референс')
        answer.update(brief=request.brief,source_id=request.source_id,mask_id=request.mask_id)
        return answer
    except HTTPException: raise
    except Exception as error: raise HTTPException(400,f'План не створено: {error}')
    finally: GPU_LOCK.release()

class Plan(BaseModel):
    workflow_id:str
    brief:str=Field(min_length=3,max_length=4000)
    prompt:str=Field(min_length=3,max_length=4000)
    negative_prompt:str=Field(default='',max_length=2000)
    reference_ids:list[str]=Field(default_factory=list,max_length=4)
    source_id:str|None=None
    mask_id:str|None=None
    rationale:str=''
    agent_model:str|None=None
    agent_seconds:float|None=None
    agent_evidence:dict|None=None
    reference_weight:float=Field(default=0.55,ge=0,le=1)
    denoise:float=Field(default=0.85,ge=0.1,le=1)

class RunRequest(BaseModel):
    plan:Plan
    variants:int=Field(default=1,ge=1,le=4)
    seed:int|None=Field(default=None,ge=0,le=2**53-4)
    request_id:uuid.UUID

def validate_plan(plan):
    if plan.workflow_id not in {x['id'] for x in catalog()}: raise ValueError('Операція не підтримується')
    if len(set(plan.reference_ids))!=len(plan.reference_ids): raise ValueError('Референси не повинні повторюватися')
    if set(plan.reference_ids)-{r['id'] for r in library()}: raise ValueError('Невідомий референс')
    if plan.workflow_id=='concept_generate':
        if not plan.reference_ids: raise ValueError('Виберіть хоча б один референс')
        if plan.source_id or plan.mask_id: raise ValueError('Для нового концепту очистіть вихідне зображення та маску або виберіть редагування')
    else:
        if not plan.source_id or not plan.mask_id: raise ValueError('Редагування потребує оригіналу та маски')
        validate_edit(resolve_asset(plan.source_id),resolve_asset(plan.mask_id))

@app.post('/api/jobs')
def submit(request:RunRequest):
    try: validate_plan(request.plan)
    except ValueError as error: raise HTTPException(400,str(error))
    # Deterministic IDs per request protect retries/double-clicks from duplicate generation.
    batch=[]
    for i in range(request.variants):
        job_id=str(uuid.uuid5(request.request_id,str(i)))
        old=get_job(job_id)
        if old:
            if old['plan']!=request.plan.model_dump(): raise HTTPException(409,'Цей request_id вже використаний для іншого запиту')
            batch.append(old); continue
        job={'id':job_id,'request_id':str(request.request_id),'status':'queued','created':time.time(),
             'plan':request.plan.model_dump(),'seed':(request.seed+i if request.seed is not None else secrets.randbits(48)),
             'parent_id':request.plan.source_id,'prompt_id':None,'error':None}
        put_job(job); WORK.put(job_id); batch.append(job)
    return batch

@app.get('/api/jobs')
def list_jobs(): return jobs()

@app.get('/api/jobs/{job_id}')
def job_detail(job_id:str):
    job=get_job(job_id)
    if not job: raise HTTPException(404,'Завдання не знайдено')
    return job

@app.post('/api/jobs/{job_id}/recover')
def recover(job_id:str):
    job=get_job(job_id)
    if not job: raise HTTPException(404,'Завдання не знайдено')
    if job['status']!='waiting' or not job.get('prompt_id'): raise HTTPException(409,'Відновлення доступне лише для очікування відомого prompt_id')
    job['status']='running'; put_job(job); WORK.put(job_id); return job

class Review(BaseModel):
    useful:str=Field(pattern='^(yes|no|unsure)$')
    comment:str=Field(default='',max_length=3000)

@app.post('/api/jobs/{job_id}/review')
def review(job_id:str, value:Review):
    job=get_job(job_id)
    if not job or job['status']!='completed': raise HTTPException(400,'Оцінити можна завершене завдання')
    job['review']={**value.model_dump(),'at':time.time()}; put_job(job); return job

@app.get('/api/health')
async def health():
    async def probe(url):
        try:
            async with httpx.AsyncClient(timeout=3,trust_env=False) as client:
                response=await client.get(url); response.raise_for_status(); return response.json()
        except Exception: return None
    comfy,ollama=await asyncio.gather(probe(CONFIG['services']['comfy_url']+'/system_stats'),probe(CONFIG['services']['ollama_url']+'/api/tags'))
    return {'comfy':comfy is not None,'ollama':ollama is not None,'agent_model':CONFIG['services']['agent_model'],
            'agent_available':bool(ollama and any(m['name']==CONFIG['services']['agent_model'] for m in ollama.get('models',[]))),
            'busy':GPU_LOCK.locked(),'queue_size':WORK.qsize()}
