import pathlib, subprocess, sys
import pytest

CHECK=pathlib.Path(__file__).resolve().parents[1]/'scripts/check_repository.py'

@pytest.mark.parametrize('name,content,allowed',[
    ('notes.md',b'# Small text file\n',True),
    ('reference.PNG',b'forced-staging-test',False),
    ('weights.safetensors',b'forced-staging-test',False),
    ('large.txt',b'x'*(256*1024+1),False),
    ('hidden.txt',b'header\x00binary',False),
    ('pointer.txt',b'version https://git-lfs.github.com/spec/v1\n',False),
],ids=['text','image','model','oversized','binary','lfs'])
def test_repository_guard(tmp_path,name,content,allowed):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    (tmp_path/name).write_bytes(content)
    subprocess.run(['git','add',name],cwd=tmp_path,check=True)
    result=subprocess.run([sys.executable,str(CHECK)],cwd=tmp_path,capture_output=True,text=True)
    assert (result.returncode==0)==allowed,result.stdout+result.stderr
