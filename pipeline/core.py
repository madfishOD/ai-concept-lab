from __future__ import annotations
import hashlib, json, pathlib, sqlite3, time, tomllib, uuid
from PIL import Image, ImageOps, ImageFilter
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
for name in ('uploads', 'jobs', 'logs'):
    (DATA / name).mkdir(parents=True, exist_ok=True)
CONFIG = tomllib.loads((ROOT / 'config.toml').read_text('utf-8'))
if (ROOT / 'config.local.toml').exists():
    for section, values in tomllib.loads((ROOT / 'config.local.toml').read_text('utf-8')).items():
        CONFIG.setdefault(section, {}).update(values)

def read_json(path):
    return json.loads(pathlib.Path(path).read_text('utf-8'))

def write_json(path, value):
    path = pathlib.Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')
    temporary.replace(path)

def digest(path):
    with pathlib.Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def library():
    return read_json(ROOT / 'library' / 'index.json')

def catalog():
    return read_json(ROOT / 'workflows' / 'catalog.json')

def db():
    con = sqlite3.connect(DATA / 'pipeline.sqlite3', timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    return con

def initialize():
    with db() as con:
        con.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, payload TEXT NOT NULL)')

def put_job(job):
    job['updated'] = time.time()
    with db() as con:
        con.execute('INSERT INTO jobs VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, updated=excluded.updated, payload=excluded.payload',
                    (job['id'], job['status'], job['created'], job['updated'], json.dumps(job, ensure_ascii=False)))
    folder = DATA / 'jobs' / job['id']; folder.mkdir(exist_ok=True)
    write_json(folder / 'manifest.json', job)

def get_job(job_id):
    with db() as con:
        row = con.execute('SELECT payload FROM jobs WHERE id=?', (job_id,)).fetchone()
    return json.loads(row[0]) if row else None

def jobs():
    with db() as con:
        return [json.loads(row[0]) for row in con.execute('SELECT payload FROM jobs ORDER BY created DESC LIMIT 200')]

def resolve_asset(asset_id):
    # IDs only. Never accept a filesystem path from browser/model.
    try: normalized = str(uuid.UUID(asset_id))
    except (ValueError, TypeError, AttributeError): raise ValueError('Некоректний ідентифікатор зображення')
    upload = DATA / 'uploads' / (normalized + '.png')
    if upload.exists(): return upload
    output = DATA / 'jobs' / normalized / 'result.png'
    if output.exists(): return output
    raise ValueError('Зображення не знайдено')

def validate_edit(source_path, mask_path):
    with Image.open(source_path) as src, Image.open(mask_path) as raw_mask:
        channels = np.asarray(raw_mask.convert('RGB'))
        if not (np.array_equal(channels[:,:,0],channels[:,:,1]) and np.array_equal(channels[:,:,1],channels[:,:,2])):
            raise ValueError('Маска має бути у відтінках сірого, без кольорових областей')
        if 'A' in raw_mask.getbands() and raw_mask.getchannel('A').getextrema() != (255,255):
            raise ValueError('Маска має бути непрозорою: використовуйте біле й чорне, не alpha')
        mask = raw_mask.convert('L')
        if src.size != mask.size:
            raise ValueError('Маска повинна мати той самий розмір, що й оригінал')
        if mask.getextrema()[1] == 0:
            raise ValueError('Маска порожня: білим позначте область редагування')

def strict_composite(source_path, generated_path, mask_path, destination, feather=4):
    validate_edit(source_path, mask_path)
    source = Image.open(source_path)
    source = source.convert('RGBA' if 'A' in source.getbands() else 'RGB')
    generated = Image.open(generated_path).convert(source.mode).resize(source.size, Image.Resampling.LANCZOS)
    mask = Image.open(mask_path).convert('L')
    values = np.asarray(mask, dtype=np.uint8)
    # Blur may extend outward; clip alpha to original mask support and weight.
    softened = np.asarray(mask.filter(ImageFilter.GaussianBlur(feather)), dtype=np.uint8) if feather else values
    alpha = np.minimum(values, softened).astype(np.float32) / 255.0
    original = np.asarray(source); replacement = np.asarray(generated)
    result = np.rint(original * (1-alpha[..., None]) + replacement * alpha[..., None]).astype(np.uint8)
    result[values == 0] = original[values == 0]
    Image.fromarray(result).save(destination)
    outside = values == 0
    difference = np.abs(result.astype(np.int16) - original.astype(np.int16))
    return {'outside_changed_pixels': int(np.any(difference[outside] != 0, axis=-1).sum()),
            'outside_max_difference': int(difference[outside].max()) if outside.any() else 0,
            'outside_pixels': int(outside.sum()), 'mask_pixels': int((values > 0).sum()),
            'feather_pixels': feather, 'source_size': list(source.size)}

def prepare_edit(source_path, mask_path, output_dir):
    validate_edit(source_path, mask_path)
    image = Image.open(source_path).convert('RGB')
    mask = Image.open(mask_path).convert('L')
    # Match exact aspect ratio by padding to multiples of 8, then undo padding at finish.
    scale = min(1.0, 1280 / max(image.size))
    scaled = tuple(max(8, round(x * scale)) for x in image.size)
    padded = tuple((x + 7) // 8 * 8 for x in scaled)
    canvas = Image.new('RGB', padded, (128,128,128)); canvas.paste(image.resize(scaled, Image.Resampling.LANCZOS), (0,0))
    mask_canvas = Image.new('L', padded, 0); mask_canvas.paste(mask.resize(scaled, Image.Resampling.NEAREST), (0,0))
    source_output = pathlib.Path(output_dir) / 'working-source.png'; mask_output = pathlib.Path(output_dir) / 'working-mask.png'
    canvas.save(source_output); mask_canvas.save(mask_output)
    return source_output, mask_output, {'scaled_size':list(scaled), 'padded_size':list(padded)}
