from __future__ import annotations
import json, queue, shutil, threading, time
from PIL import Image, ImageOps
from .core import DATA, ROOT, CONFIG, catalog, library, get_job, put_job, jobs, resolve_asset, digest, write_json, prepare_edit, strict_composite
from .services import ComfyClient
from .workflows import build

GPU_LOCK=threading.Lock()
WORK=queue.Queue()

def run_job(job):
    folder=DATA/'jobs'/job['id']; folder.mkdir(exist_ok=True)
    plan=job['plan']; client=ComfyClient(); start=time.monotonic()
    if not job.get('prompt_id'):
        # Probe before transitioning to submitting. A later lost response is never blindly retried.
        client.request('GET','/system_stats')
        if client.queue().get('queue_running') or client.queue().get('queue_pending'):
            raise RuntimeError('ComfyUI зайнятий іншим завданням. Повторіть запуск після завершення черги.')
        refs=[]; provenance=[]
        index={r['id']:r for r in library()}
        if plan['workflow_id']=='concept_generate':
            for i,ref_id in enumerate(plan['reference_ids']):
                ref=index[ref_id]; original=ROOT/'library'/ref['file']
                snapshot=folder/f'reference-{i}.png'; shutil.copy2(original,snapshot)
                # Square letterboxing avoids CLIP's center crop cutting off full-body silhouettes.
                with Image.open(snapshot) as image:
                    preview=ImageOps.pad(image.convert('RGB'),(768,768),color=(224,224,224))
                    prepared=folder/f'reference-{i}-padded.png'; preview.save(prepared)
                refs.append(client.upload(prepared,f"{job['id']}-ref-{i}.png"))
                provenance.append({'id':ref_id,'sha256':digest(snapshot),'snapshot':snapshot.name,'status':ref['status']})
        source_name=mask_name=None
        if plan['workflow_id']=='concept_edit_masked':
            source=resolve_asset(plan['source_id']); mask=resolve_asset(plan['mask_id'])
            shutil.copy2(source,folder/'source.png'); shutil.copy2(mask,folder/'mask.png')
            source_work,mask_work,transform=prepare_edit(source,mask,folder)
            job['edit_transform']=transform
            source_name=client.upload(source_work,job['id']+'-source.png')
            mask_name=client.upload(mask_work,job['id']+'-mask.png')
            provenance=[{'role':'source','sha256':digest(folder/'source.png')},{'role':'mask','sha256':digest(folder/'mask.png')}]
        graph=build(plan,job['seed'],job['id'],refs,source_name,mask_name)
        write_json(folder/'workflow.api.json',graph)
        job['provenance']=provenance
        job['workflow_sha256']=digest(folder/'workflow.api.json')
        job['generation_config']=CONFIG['generation'].copy()
        job['workflow_version']=next(x['version'] for x in catalog() if x['id']==plan['workflow_id'])
        if (ROOT/'runtime-manifest.json').exists(): job['runtime_manifest']=json.loads((ROOT/'runtime-manifest.json').read_text('utf-8'))
        job['status']='submitting'; put_job(job)
        try:
            job['prompt_id']=client.submit(graph,job['id'])
        except Exception as error:
            job['status']='submission_unknown'; job['error']=f'Не вдалося підтвердити постановку в чергу. Автоповтор вимкнено: {error}'
            put_job(job); return
        job['status']='running'; put_job(job)
    while time.monotonic()-start < CONFIG['generation']['timeout_seconds']:
        try: history=client.history(job['prompt_id'])
        except Exception:
            time.sleep(3); continue
        if history:
            write_json(folder/'comfy-history.json',history)
            status=history.get('status',{})
            if status.get('status_str')=='error':
                raise RuntimeError('Помилка виконання ComfyUI: '+json.dumps(status.get('messages',[]),ensure_ascii=False)[-2000:])
            entries=history.get('outputs',{}).get('7',{}).get('images',[])
            if entries:
                (folder/'raw.png').write_bytes(client.output(entries[0]))
                if plan['workflow_id']=='concept_edit_masked':
                    scaled=job['edit_transform']['scaled_size']
                    with Image.open(folder/'raw.png') as raw:
                        raw.crop((0,0,*scaled)).save(folder/'generated-unpadded.png')
                    job['mask_validation']=strict_composite(folder/'source.png',folder/'generated-unpadded.png',folder/'mask.png',folder/'result.png')
                    if job['mask_validation']['outside_changed_pixels']:
                        raise RuntimeError('Strict mask verification failed')
                else:
                    shutil.copy2(folder/'raw.png',folder/'result.png')
                job['status']='completed'; job['output_id']=job['id']; job['output_sha256']=digest(folder/'result.png')
                job['execution_seconds']=round(time.monotonic()-start,2); job['error']=None
                put_job(job); return
        time.sleep(2)
    job['status']='waiting'; job['error']='Час очікування минув. Завдання не дубльовано; перевірте той самий prompt_id кнопкою «Перевірити».'
    put_job(job)

def worker():
    while True:
        job_id=WORK.get()
        try:
            with GPU_LOCK:
                job=get_job(job_id)
                if not job or job['status'] not in ('queued','running','waiting'): continue
                try:
                    if job['status']=='queued': job['status']='preparing'; put_job(job)
                    run_job(job)
                except Exception as error:
                    job['status']='failed'; job['error']=str(error); put_job(job)
        finally: WORK.task_done()

def start_worker():
    # Resume only known submitted IDs. An interrupted submit needs reconciliation, not retry.
    for job in reversed(jobs()):
        if job['status'] in ('submitting','preparing'):
            if job.get('prompt_id'): job['status']='running'
            elif job['status']=='preparing': job['status']='queued'
            else: job['status']='submission_unknown'; job['error']='Перезапуск під час submit; потрібна перевірка ComfyUI, автоматичного дублювання немає.'
            put_job(job)
        if job['status'] in ('queued','running','waiting'): WORK.put(job['id'])
    threading.Thread(target=worker,name='generation-worker',daemon=True).start()
