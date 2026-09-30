"""Assemble existing local outputs for human review; does not generate or retouch content."""
import json,pathlib
from PIL import Image,ImageOps,ImageDraw,ImageFont
ROOT=pathlib.Path(__file__).resolve().parent.parent
OUT=ROOT/'data/experiments/first-local-pilot'
records=json.loads((OUT/'results.json').read_text('utf-8'))
ids={item['case']:item['job_id'] for item in records if item.get('job_id')}
source=next(item['source_id'] for item in records if item['case']=='fixtures')
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
def sheet(items,path):
    result=Image.new('RGB',(len(items)*350,570),(28,27,36));draw=ImageDraw.Draw(result)
    for i,(label,job_id) in enumerate(items):
        image=Image.open(ROOT/'data/jobs'/job_id/'result.png').convert('RGB')
        thumbnail=ImageOps.contain(image,(334,500))
        result.paste(thumbnail,(i*350+(350-thumbnail.width)//2,54))
        draw.text((i*350+16,16),label,font=font,fill=(225,218,239))
    result.save(path)
sheet([('Manual / duelist',source),('Qwen / guardian',ids['generate-knight']),('Qwen / bell keeper',ids['generate-mystic'])],OUT/'generation-review.jpg')
sheet([('Source',source),('Shoulder edit',ids['edit-shoulder']),('Face edit',ids['edit-face']),('Weapon edit',ids['edit-weapon'])],OUT/'edit-review.jpg')
print('Review sheets saved.')
