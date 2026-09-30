"""Verify the final router/visual-planner contract and render one corrected edit."""
import json,pathlib,re,time,uuid,sys
import httpx
sys.stdout.reconfigure(encoding='utf-8')
ROOT=pathlib.Path(__file__).resolve().parent.parent
OUT=ROOT/'data/experiments/first-local-pilot'
fixtures=next(x for x in json.loads((OUT/'results.json').read_text('utf-8')) if x['case']=='fixtures')
with httpx.Client(timeout=300,trust_env=False) as client:
    cases=[('final-generation-plan',{'brief':'Новий концепт Nocturna: жінка-мисливиця у темному готичному плащі з арбалетом, повний зріст, прості форми.','reference_ids':['NOC003','NOC004','NOC006']}),
           ('final-edit-plan',{'brief':'Заміни наплічник на простий округлий наплічник із темно-фіолетової сталі, одна срібна кромка, без золота і без шипів.','source_id':fixtures['source_id'],'mask_id':fixtures['mask_ids']['shoulder'],'reference_ids':['NOC002','NOC003']})]
    plans=[]
    for name,request in cases:
        response=client.post('http://127.0.0.1:8765/api/plan',json=request);response.raise_for_status();plan=response.json()
        (OUT/(name+'.json')).write_text(json.dumps(plan,ensure_ascii=False,indent=2),'utf-8')
        expected='concept_generate' if 'generation' in name else 'concept_edit_masked'
        assert plan['workflow_id']==expected,plan
        assert not re.search('[А-Яа-яІіЇїЄєҐґ]',plan['prompt']+plan['negative_prompt']),plan
        print(json.dumps({'case':name,'workflow':plan['workflow_id'],'seconds':plan['agent_seconds'],'prompt':plan['prompt'],'english_repair':plan.get('agent_evidence',{}).get('english_repair',False)},ensure_ascii=False),flush=True)
        plans.append(plan)
    response=client.post('http://127.0.0.1:8765/api/jobs',json={'plan':plans[-1],'seed':404,'variants':1,'request_id':str(uuid.uuid4())});response.raise_for_status();job=response.json()[0]
    for _ in range(150):
        job=client.get('http://127.0.0.1:8765/api/jobs/'+job['id']).json()
        if job['status'] in ('completed','failed','submission_unknown','waiting'):break
        time.sleep(2)
    assert job['status']=='completed',job
    assert job['mask_validation']['outside_changed_pixels']==0
    (OUT/'final-agent-verification.json').write_text(json.dumps({'passed':True,'edit_job_id':job['id'],'seconds':job['execution_seconds'],'mask_validation':job['mask_validation']},indent=2),'utf-8')
    print('Final corrected edit:',job['id'],flush=True)
