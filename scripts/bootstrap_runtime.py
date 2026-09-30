"""Explicit, resumable local prototype bootstrap. No system PATH/registry changes."""
import concurrent.futures, json, pathlib, subprocess, time, urllib.request, zipfile

ROOT = pathlib.Path(r'D:\Work\StableDiffusion')
CACHE = ROOT / 'Downloads'
CACHE.mkdir(parents=True, exist_ok=True)
MODELS = ROOT / 'Models'

def download(url, destination):
    destination = pathlib.Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print('EXISTS', destination, flush=True)
        return destination
    temporary = destination.with_suffix(destination.suffix + '.partial')
    print('DOWNLOAD', destination.name, flush=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'ai-concept-pipeline-bootstrap/0.1'})
    with urllib.request.urlopen(req, timeout=120) as response, temporary.open('wb') as target:
        total = int(response.headers.get('Content-Length', 0)); size = 0; last = time.monotonic()
        while chunk := response.read(4 * 1024 * 1024):
            target.write(chunk); size += len(chunk)
            if time.monotonic() - last > 20:
                print(f'{destination.name}: {size / 1e9:.2f}/{total / 1e9:.2f} GB', flush=True); last = time.monotonic()
        if total and size != total:
            raise RuntimeError(f'Incomplete download: {destination}')
    temporary.replace(destination)
    print('READY', destination, flush=True)
    return destination

FILES = [
 ('https://github.com/Comfy-Org/ComfyUI/releases/download/v0.38.0/ComfyUI_windows_portable_nvidia.7z', CACHE/'ComfyUI-v0.38.0-nvidia.7z'),
 ('https://github.com/ollama/ollama/releases/download/v0.35.0/ollama-windows-amd64.zip', CACHE/'ollama-v0.35.0-windows.zip'),
 ('https://www.7-zip.org/a/7zr.exe', CACHE/'7zr.exe'),
 ('https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors', MODELS/'checkpoints/sd_xl_base_1.0.safetensors'),
 ('https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors', MODELS/'ipadapter/ip-adapter-plus_sdxl_vit-h.safetensors'),
 ('https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors', MODELS/'clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors'),
]

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(download, url, path) for url, path in FILES]
        for future in concurrent.futures.as_completed(futures): future.result()
    comfy = ROOT/'ComfyUI'
    if not (comfy/'python_embeded/python.exe').exists():
        staging = CACHE/'comfy-v0.38.0-extracted'
        subprocess.run([str(CACHE/'7zr.exe'), 'x', str(CACHE/'ComfyUI-v0.38.0-nvidia.7z'), '-o'+str(staging), '-y'], check=True, stdout=subprocess.DEVNULL)
        source = staging/'ComfyUI_windows_portable'
        comfy.mkdir(exist_ok=True)
        for item in source.iterdir():
            target = comfy/item.name
            if target.exists(): raise RuntimeError(f'Refusing to replace existing path: {target}')
            item.rename(target)
    ollama = ROOT/'Ollama'
    if not (ollama/'ollama.exe').exists():
        ollama.mkdir(exist_ok=True)
        with zipfile.ZipFile(CACHE/'ollama-v0.35.0-windows.zip') as archive: archive.extractall(ollama)
    (ROOT/'bootstrap-manifest.json').write_text(json.dumps({'comfyui':'v0.38.0','ollama':'v0.35.0','downloads':[{'url':u,'path':str(p),'bytes':p.stat().st_size} for u,p in FILES]}, indent=2), encoding='utf-8')
    print('BOOTSTRAP COMPLETE', flush=True)
