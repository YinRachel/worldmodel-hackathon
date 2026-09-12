"""Runware inpainting integration. Keys remain server-side."""
import base64
import io
import json
import os
from pathlib import Path
import urllib.request
import urllib.error
import uuid
from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parent

def data_uri(image):
    out = io.BytesIO()
    image.save(out, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()

def composite(original, generated, mask):
    # Feather inward only: pixels outside the selected region remain identical.
    alpha = ImageChops.multiply(mask.filter(ImageFilter.GaussianBlur(3)), mask)
    return Image.composite(generated.resize(original.size, Image.Resampling.LANCZOS), original, alpha)

def delete_object(mask_bytes, clear_room=False, image_path=None):
    key = os.environ.get('RUNWARE_API_KEY', '').strip()
    if not key:
        key = (ROOT / 'runware_api_key.txt').read_text().strip()
    original = Image.open(image_path or ROOT / 'picture/IMG_9219.jpeg').convert('RGB')
    mask = Image.open(io.BytesIO(mask_bytes)).convert('L')
    if mask.size != original.size or mask.getextrema() != (0, 255):
        raise ValueError('Select part of the room with a black-and-white mask.')
    scale = min(1024 / original.width, 1024 / original.height)
    size = tuple(max(64, round(value * scale / 64) * 64) for value in original.size)
    task = {
        'taskType': 'imageInference', 'taskUUID': str(uuid.uuid4()),
        'model': 'runware:102@1', 'numberResults': 1,
        'positivePrompt': ('An empty unfurnished room. Reconstruct plain off-white walls, white baseboards and continuous green and grey carpet where the selected furniture used to be. Match the existing room geometry, perspective, carpet boundary and lighting. Bare unobstructed floor, no furniture or objects.' if clear_room else 'Empty green carpet floor, continuous mottled green carpet texture matching the surrounding floor, realistic indoor lighting and perspective, unobstructed floor.'),
        'seedImage': data_uri(original.resize(size, Image.Resampling.LANCZOS)),
        'maskImage': data_uri(mask.resize(size, Image.Resampling.NEAREST)),
        'width': size[0], 'height': size[1], 'steps': 40, 'CFGScale': 30,
        'outputType': 'base64Data', 'outputFormat': 'PNG',
    }
    request = urllib.request.Request('https://api.runware.ai/v1',
        data=json.dumps([task]).encode(),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        # Do not expose raw responses that could contain request credentials.
        raise ValueError(f'Runware returned HTTP {exc.code}. Check the API key, credits and model access.') from None
    except urllib.error.URLError:
        raise ValueError('Cannot reach Runware. Check network access.') from None
    if result.get('errors'):
        messages = [str(e.get('message', 'Request rejected')) for e in result['errors']]
        raise ValueError('; '.join(messages).replace(key, '[REDACTED]')[:1000])
    rows = result.get('data', [])
    row = next((r for r in rows if r.get('imageBase64Data')), None)
    if not row:
        raise ValueError('Runware did not return an image. No automatic retry was made.')
    encoded = row['imageBase64Data'].split(',')[-1]
    generated = Image.open(io.BytesIO(base64.b64decode(encoded))).convert('RGB')
    edited = composite(original, generated, mask)
    name = 'runware-deleted-' + uuid.uuid4().hex + '.png'
    path = ROOT / 'outputs' / name
    path.parent.mkdir(exist_ok=True)
    edited.save(path)
    return name
