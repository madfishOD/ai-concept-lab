import hashlib,json,pathlib,subprocess,sys
import httpx
ROOT=pathlib.Path(__file__).resolve().parent.parent
manifest=json.loads((ROOT/'runtime-manifest.json').read_text('utf-8'))
lock=[]
for record in manifest['downloads']:
    path=pathlib.Path(record['path'])
    if path.suffix!='.safetensors':continue
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    lock.append({'url':record['url'],'bytes':record['bytes'],'relative_path':path.relative_to(pathlib.Path(r'D:\Work\StableDiffusion\Models')).as_posix(),'sha256':digest})
with httpx.Client(timeout=10,trust_env=False) as client:
    tags=client.get('http://127.0.0.1:11434/api/tags').json()
    manifest['ollama_models']=tags['models']
    manifest['comfy_system']=client.get('http://127.0.0.1:8188/system_stats').json()
manifest['app_python']=sys.version
(ROOT/'models.lock.json').write_text(json.dumps(lock,indent=2),'utf-8')
(ROOT/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2),'utf-8')
embedded=pathlib.Path(r'D:\Work\StableDiffusion\ComfyUI\python_embeded\python.exe')
with (ROOT/'comfy-requirements.lock.txt').open('w') as stream:
    subprocess.run([str(embedded),'-m','pip','freeze'],stdout=stream,check=True)
print('Recorded model SHA-256 hashes, Ollama digest, runtime versions and Comfy dependency snapshot.')
