"""Reject assets and large/binary content in the Git index (stdlib only)."""
import pathlib, subprocess, sys

FORBIDDEN={'.png','.jpg','.jpeg','.webp','.gif','.bmp','.tga','.tif','.tiff','.exr','.hdr','.psd','.psb','.svg','.ico','.avif','.heic',
           '.safetensors','.gguf','.ckpt','.pt','.pth','.bin','.onnx','.h5','.npz','.npy',
           '.fbx','.obj','.blend','.glb','.gltf','.7z','.zip','.exe','.dll','.whl','.tar','.gz','.mp4','.mov','.pdf'}
MAX_FILE=256*1024
MAX_TOTAL=2*1024*1024

def git(*args): return subprocess.check_output(['git',*args])

def main():
    root=git('rev-parse','--show-toplevel').decode().strip()
    import os
    os.chdir(root)
    entries=git('ls-files','--stage','-z').split(b'\0')
    errors=[];total=0;count=0
    for entry in entries:
        if not entry: continue
        metadata,raw_path=entry.split(b'\t',1)
        mode,oid,stage=metadata.decode().split()
        path=raw_path.decode('utf-8');count+=1
        if stage!='0': errors.append(f'{path}: unresolved merge');continue
        if mode=='160000': errors.append(f'{path}: submodules are outside this minimal repository');continue
        size=int(git('cat-file','-s',oid));total+=size
        if pathlib.PurePosixPath(path).suffix.lower() in FORBIDDEN:
            errors.append(f'{path}: image/model/binary asset extension is forbidden')
        if size>MAX_FILE:
            errors.append(f'{path}: {size} bytes exceeds {MAX_FILE}');continue
        content=git('cat-file','blob',oid)
        try: content.decode('utf-8')
        except UnicodeDecodeError: errors.append(f'{path}: only UTF-8 text belongs in this repository')
        if b'\0' in content: errors.append(f'{path}: binary content')
        if content.startswith(b'version https://git-lfs.github.com/spec/v1'):
            errors.append(f'{path}: Git LFS assets are not allowed')
    if total>MAX_TOTAL: errors.append(f'Index total {total} bytes exceeds {MAX_TOTAL}')
    for error in errors: print('ERROR:',error)
    print(f'Checked {count} indexed files, {total:,} bytes; '+('FAILED' if errors else 'text-only policy OK'))
    return bool(errors)

if __name__=='__main__': sys.exit(main())
