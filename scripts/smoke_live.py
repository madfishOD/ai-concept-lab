"""Explicit live GPU integration experiment; creates visible jobs and artifacts, no mocked renders."""
import json, pathlib, sys, time, uuid
import httpx
from PIL import Image, ImageDraw
sys.stdout.reconfigure(encoding='utf-8')

ROOT=pathlib.Path(__file__).resolve().parent.parent
OUT=ROOT/'data/experiments/first-local-pilot';OUT.mkdir(parents=True,exist_ok=True)
API='http://127.0.0.1:8765'
client=httpx.Client(timeout=300,trust_env=False)
results=json.loads((OUT/'results.json').read_text('utf-8')) if (OUT/'results.json').exists() else []

def post(path,payload):
    response=client.post(API+path,json=payload)
    response.raise_for_status();return response.json()

def record(case,data):
    results[:] = [entry for entry in results if entry['case']!=case]
    entry={'case':case,**data};results.append(entry)
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(entry,ensure_ascii=False),flush=True)

def upload(path):
    with path.open('rb') as stream:
        response=client.post(API+'/api/uploads',files={'file':(path.name,stream,'image/png')})
    response.raise_for_status();return response.json()['id']

def wait(job_id):
    started=time.monotonic()
    while time.monotonic()-started<600:
        job=client.get(API+'/api/jobs/'+job_id).json()
        if job['status'] in ('completed','failed','submission_unknown','waiting'):
            if job['status']!='completed': raise RuntimeError(json.dumps(job,ensure_ascii=False))
            return job
        time.sleep(2)
    raise TimeoutError(job_id)

def execute(case,plan,seed):
    existing=next((entry for entry in results if entry['case']==case and entry.get('status')=='completed'),None)
    if existing: return client.get(API+'/api/jobs/'+existing['job_id']).json()
    request={'plan':plan,'variants':1,'seed':seed,'request_id':str(uuid.uuid4())}
    submitted=post('/api/jobs',request)
    # Retry same request intentionally: must return the same ID, not a second render.
    repeated=post('/api/jobs',request)
    assert submitted[0]['id']==repeated[0]['id']
    job=wait(submitted[0]['id'])
    record(case,{'job_id':job['id'],'status':job['status'],'seconds':job['execution_seconds'],
                 'mask_validation':job.get('mask_validation'),'duplicate_request_same_id':True})
    return job

def agent_plan(case,brief,source_id=None,mask_id=None,refs=None):
    cached=OUT/(case+'-plan.json')
    if cached.exists() and case not in ('agent-missing-mask','agent-unsupported'):
        plan=json.loads(cached.read_text('utf-8'))
        plan.update(source_id=source_id,mask_id=mask_id)
        return plan
    plan=post('/api/plan',{'brief':brief,'source_id':source_id,'mask_id':mask_id,'reference_ids':refs or []})
    (OUT/(case+'-plan.json')).write_text(json.dumps(plan,ensure_ascii=False,indent=2),'utf-8')
    record(case,{'operation':plan['workflow_id'],'seconds':plan.get('agent_seconds'),'references':plan.get('reference_ids'),'rationale':plan.get('rationale'),'question':plan.get('question'),'contract_correction':plan.get('agent_evidence',{}).get('contract_correction')})
    return plan

if __name__=='__main__':
    first=next(j for j in reversed(client.get(API+'/api/jobs').json()) if j['status']=='completed')
    source_id=first['id'];source_path=ROOT/'data/jobs'/source_id/'result.png'
    original=Image.open(source_path);w,h=original.size
    masks={
        'shoulder':[(0.245*w,0.145*h),(0.445*w,0.145*h),(0.455*w,0.285*h),(0.26*w,0.29*h)],
        'face':[(0.4*w,0.045*h),(0.575*w,0.045*h),(0.575*w,0.185*h),(0.4*w,0.185*h)],
        'weapon':[(0,0.425*h),(0.265*w,0.375*h),(0.30*w,0.48*h),(0.055*w,0.66*h),(0,0.66*h)],
    }
    mask_ids={}
    for name,points in masks.items():
        mask=Image.new('L',original.size,0);ImageDraw.Draw(mask).polygon(points,fill=255)
        path=OUT/(name+'-mask.png');mask.save(path);mask_ids[name]=upload(path)
    record('fixtures',{'source_id':source_id,'mask_ids':mask_ids,'note':'Programmatic test masks, not artist-authored approvals.'})
    # Genuine end-to-end local agent -> ComfyUI for two distinct concept briefs.
    knight=agent_plan('agent-knight','Створи нового чоловіка Nocturna: масивний вартовий склепу у простому готичному обладунку, одна велика булава та щит. Повний зріст, світло-сірий фон. Помірний декор, основа для paintover.')
    assert knight['workflow_id']=='concept_generate'
    execute('generate-knight',knight,202)
    mystic=agent_plan('agent-mystic','Створи нового персонажа Nocturna: літній хранитель похоронного дзвону, довгий фіолетовий одяг з великими простими складками, один посох із бронзовим дзвоном. Повний зріст, світлий нейтральний фон, небагато дрібного декору.')
    assert mystic['workflow_id']=='concept_generate'
    execute('generate-mystic',mystic,303)
    shoulder=agent_plan('agent-shoulder','Заміни тільки позначений наплічник: простий великий округлий наплічник із темно-фіолетової сталі, одна срібна кромка, без золота та без шипів. Збережи стиль персонажа.',source_id,mask_ids['shoulder'],['NOC002','NOC003'])
    assert shoulder['workflow_id']=='concept_edit_masked'
    execute('edit-shoulder',shoulder,404)
    common={'workflow_id':'concept_edit_masked','source_id':source_id,'negative_prompt':'photorealistic, distorted, text, watermark, intricate filigree','reference_ids':[],'denoise':0.9}
    execute('edit-face',{**common,'brief':'Тест: змінити обличчя на старшу жінку зі шрамом.','prompt':'Face of a mature female vampire duelist, visible scar across one eyebrow, stern expression, pale skin, white hair, stylized game character, sculpted facial planes, same lighting','mask_id':mask_ids['face']},505)
    execute('edit-weapon',{**common,'brief':'Тест: замінити позначений клинок на широкий вигнутий клинок.','prompt':'One broad curved dark steel saber blade with a simple silver cutting edge, clearly readable single weapon silhouette, stylized game weapon, broad planes, no ornament','mask_id':mask_ids['weapon']},606)
    missing=agent_plan('agent-missing-mask','Зміни наплічник на цьому персонажі.',source_id=source_id,refs=['NOC002'])
    assert missing['workflow_id']=='clarify'
    unsupported=agent_plan('agent-unsupported','Зроби анімацію бігу та готовий ріг цього персонажа.',source_id=source_id,refs=['NOC002'])
    assert unsupported['workflow_id']=='unsupported'
    record('complete',{'passed':True})
