import uuid
import numpy as np
import pytest
from PIL import Image
from pipeline.core import strict_composite, validate_edit, prepare_edit, resolve_asset
from pipeline.workflows import build
from pipeline.app import Plan, validate_plan
from pipeline.app import Brief
from pipeline.services import enforce_plan_contract

def make_images(tmp_path):
    rng=np.random.default_rng(42)
    original=rng.integers(0,256,(79,101,3),dtype=np.uint8)
    Image.fromarray(original).save(tmp_path/'source.png')
    Image.new('RGB',(64,64),'red').save(tmp_path/'generated.png')
    mask=np.zeros((79,101),dtype=np.uint8);mask[15:55,30:70]=255;mask[25:35,40:50]=0
    Image.fromarray(mask).save(tmp_path/'mask.png')
    return original,mask

def test_strict_mask_preserves_every_outside_pixel_including_hole(tmp_path):
    original,mask=make_images(tmp_path)
    result=strict_composite(tmp_path/'source.png',tmp_path/'generated.png',tmp_path/'mask.png',tmp_path/'result.png',feather=4)
    actual=np.asarray(Image.open(tmp_path/'result.png'))
    assert np.array_equal(actual[mask==0],original[mask==0])
    assert np.any(actual[mask==255]!=original[mask==255])
    assert result['outside_changed_pixels']==0

def test_invalid_mask_is_rejected(tmp_path):
    make_images(tmp_path)
    Image.new('L',(101,79),0).save(tmp_path/'empty.png')
    with pytest.raises(ValueError,match='порожня'): validate_edit(tmp_path/'source.png',tmp_path/'empty.png')
    Image.new('L',(100,79),255).save(tmp_path/'wrong.png')
    with pytest.raises(ValueError,match='розмір'): validate_edit(tmp_path/'source.png',tmp_path/'wrong.png')

def test_edit_preparation_pads_without_crop(tmp_path):
    original,mask=make_images(tmp_path)
    source,prepared_mask,transform=prepare_edit(tmp_path/'source.png',tmp_path/'mask.png',tmp_path)
    assert transform['scaled_size']==[101,79]
    assert Image.open(source).size==(104,80)
    assert np.array_equal(np.asarray(Image.open(source))[:79,:101],original)
    assert np.asarray(Image.open(prepared_mask))[:,101:].max()==0

def test_transparent_source_is_preserved_outside_mask(tmp_path):
    original,mask=make_images(tmp_path)
    rgba=np.dstack([original,np.random.default_rng(3).integers(0,256,(79,101),dtype=np.uint8)])
    Image.fromarray(rgba).save(tmp_path/'source.png')
    strict_composite(tmp_path/'source.png',tmp_path/'generated.png',tmp_path/'mask.png',tmp_path/'result.png')
    assert np.array_equal(np.asarray(Image.open(tmp_path/'result.png'))[mask==0],rgba[mask==0])

def test_color_and_transparent_masks_are_rejected(tmp_path):
    make_images(tmp_path)
    Image.new('RGB',(101,79),'red').save(tmp_path/'colored.png')
    with pytest.raises(ValueError,match='сірого'): validate_edit(tmp_path/'source.png',tmp_path/'colored.png')
    Image.new('RGBA',(101,79),(255,255,255,120)).save(tmp_path/'alpha.png')
    with pytest.raises(ValueError,match='непрозорою'): validate_edit(tmp_path/'source.png',tmp_path/'alpha.png')

@pytest.mark.parametrize('path',['../../PLAN.md',r'D:\secret.png','not-an-id'])
def test_assets_do_not_accept_paths(path):
    with pytest.raises(ValueError): resolve_asset(path)

def test_generate_requires_references():
    with pytest.raises(ValueError,match='референс'):
        validate_plan(Plan(workflow_id='concept_generate',brief='test',prompt='test'))

def test_edit_does_not_fall_back_without_mask():
    with pytest.raises(ValueError,match='маски'):
        validate_plan(Plan(workflow_id='concept_edit_masked',brief='test',prompt='test'))

def test_generation_graph_receives_actual_images():
    graph=build({'workflow_id':'concept_generate','prompt':'p','negative_prompt':'n'},12,str(uuid.uuid4()),['a.png','b.png'])
    assert graph['10']['inputs']['image']=='a.png'
    assert graph['20']['inputs']['image']=='b.png'
    assert graph['11']['inputs']['image']==['21',0]
    assert graph['4']['inputs']['model']==['11',0]

def test_model_cannot_invent_automatic_masking():
    proposed={'workflow_id':'concept_edit_masked','prompt':'change shoulder','rationale':'I will automatically segment it','reference_ids':['NOC002']}
    request=Brief(brief='change shoulder',source_id=str(uuid.uuid4()))
    corrected=enforce_plan_contract(proposed,request)
    assert corrected['workflow_id']=='clarify'
    assert corrected['prompt']==''
    assert corrected['agent_evidence']['contract_correction']=='missing_edit_inputs'
    assert 'PNG' in corrected['question']
