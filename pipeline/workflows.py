import copy, json
from .core import ROOT, CONFIG

def node(kind, **inputs): return {'class_type':kind, 'inputs':inputs}

def templates():
    common = {
        '1': node('CheckpointLoaderSimple', ckpt_name='sd_xl_base_1.0.safetensors'),
        '2': node('CLIPTextEncode', text='PROMPT', clip=['1',1]),
        '3': node('CLIPTextEncode', text='NEGATIVE', clip=['1',1]),
        '4': node('KSampler', seed=1, steps=28, cfg=6.0, sampler_name='dpmpp_2m', scheduler='karras', denoise=1.0,
                  model=['1',0], positive=['2',0], negative=['3',0], latent_image=['5',0]),
        '6': node('VAEDecode', samples=['4',0], vae=['1',2]),
        '7': node('SaveImage', images=['6',0], filename_prefix='ai-concept-pipeline/example'),
    }
    generate = copy.deepcopy(common)
    generate.update({
        '5':node('EmptyLatentImage', width=832, height=1216, batch_size=1),
        '8':node('IPAdapterModelLoader', ipadapter_file='ip-adapter-plus_sdxl_vit-h.safetensors'),
        '9':node('CLIPVisionLoader', clip_name='CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors'),
        '10':node('LoadImage', image='REFERENCE.png'),
        '11':node('IPAdapterAdvanced', model=['1',0], ipadapter=['8',0], image=['10',0], clip_vision=['9',0],
                  weight=0.55, weight_type='style transfer', combine_embeds='average', start_at=0.0, end_at=0.85, embeds_scaling='V only'),
    })
    generate['4']['inputs']['model'] = ['11',0]
    edit = copy.deepcopy(common)
    edit.update({
        '8':node('LoadImage', image='SOURCE.png'),
        '9':node('LoadImage', image='MASK.png'),
        '10':node('ImageToMask', image=['9',0], channel='red'),
        '5':node('VAEEncodeForInpaint', pixels=['8',0], mask=['10',0], vae=['1',2], grow_mask_by=0),
    })
    edit['4']['inputs']['denoise'] = 0.85
    return {'concept_generate':generate,'concept_edit_masked':edit}

def build(plan, seed, job_id, references=None, source=None, mask=None):
    graph = json.loads((ROOT/'workflows'/f'{plan["workflow_id"]}.api.json').read_text('utf-8'))
    settings = CONFIG['generation']
    graph['1']['inputs']['ckpt_name'] = settings['checkpoint']
    graph['2']['inputs']['text'] = plan['prompt']
    graph['3']['inputs']['text'] = plan['negative_prompt']
    graph['4']['inputs'].update(seed=seed, steps=settings['steps'], cfg=settings['cfg'])
    graph['7']['inputs']['filename_prefix'] = f'ai-concept-pipeline/{job_id}'
    if plan['workflow_id'] == 'concept_generate':
        if not references: raise ValueError('Генерація потребує хоча б одного референсу')
        graph['5']['inputs'].update(width=settings['width'],height=settings['height'])
        graph['8']['inputs']['ipadapter_file'] = settings['ipadapter']
        graph['9']['inputs']['clip_name'] = settings['clip_vision']
        graph['11']['inputs']['weight'] = plan.get('reference_weight',settings['reference_weight'])
        graph['10']['inputs']['image'] = references[0]
        previous = ['10',0]
        for i, filename in enumerate(references[1:]):
            image_id = str(20+i*2); batch_id = str(21+i*2)
            graph[image_id] = node('LoadImage', image=filename)
            graph[batch_id] = node('ImageBatch', image1=previous, image2=[image_id,0])
            previous = [batch_id,0]
        graph['11']['inputs']['image'] = previous
    else:
        graph['8']['inputs']['image'] = source
        graph['9']['inputs']['image'] = mask
        graph['4']['inputs']['denoise'] = plan.get('denoise',0.85)
    return graph

if __name__ == '__main__':
    for name, graph in templates().items():
        (ROOT/'workflows'/f'{name}.api.json').write_text(json.dumps(graph,indent=2),'utf-8')
