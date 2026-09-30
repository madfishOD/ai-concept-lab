import queue, time, uuid
from types import SimpleNamespace
from pipeline import core,runner

def test_restart_resumes_known_ids_but_never_repeats_ambiguous_submission(tmp_path,monkeypatch):
    (tmp_path/'jobs').mkdir()
    monkeypatch.setattr(core,'DATA',tmp_path)
    core.initialize()
    work=queue.Queue();monkeypatch.setattr(runner,'WORK',work)
    monkeypatch.setattr(runner.threading,'Thread',lambda **kwargs:SimpleNamespace(start=lambda:None))
    entries=[]
    for status,prompt in [('running','known-123'),('submitting',None),('preparing',None),('completed','done-456')]:
        item={'id':str(uuid.uuid4()),'status':status,'prompt_id':prompt,'created':time.time()}
        core.put_job(item);entries.append(item)
    runner.start_worker()
    queued=[]
    while not work.empty():queued.append(work.get_nowait())
    assert set(queued)=={entries[0]['id'],entries[2]['id']}
    assert core.get_job(entries[0]['id'])['prompt_id']=='known-123'
    assert core.get_job(entries[1]['id'])['status']=='submission_unknown'
    assert core.get_job(entries[3]['id'])['status']=='completed'
