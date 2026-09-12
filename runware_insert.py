"""One paid Runware reference-image insertion test using the saved selection."""
import base64
import io
import json
import os
from pathlib import Path
import urllib.request
import urllib.error
import uuid

from PIL import Image
from runware_edit import data_uri

ROOT = Path(__file__).resolve().parent


def insert_sofa(state, placement):
    room = ROOT / (state.get('empty_room') or state['room_candidate']).lstrip('/')
    product = state['selected_product']
    with urllib.request.urlopen(product['image_url'], timeout=30) as response:
        sofa = Image.open(io.BytesIO(response.read())).convert('RGB')
    sofa.save(ROOT / 'outputs/selected-sofa-reference.png')
    original = Image.open(room).convert('RGB')
    original.thumbnail((1536, 1536))
    prompt = (
        'Edit reference image 1, the room photograph. Insert exactly one sofa from '
        'reference image 2 into this room. Placement instruction: ' + placement + '. Use perspective '
        'consistent with the room. Preserve the reference sofa design, color, '
        'upholstery, arm shape, cushion arrangement and legs. Use only the sofa from '
        'image 2, not its background. Make it a plausible full-size sofa, '
        'grounded on the floor with natural contact shadows and matching indoor light. '
        'Keep all existing room objects, walls, ceiling, doors, carpet, camera position '
        'and framing unchanged. Do not overlap the existing table. Output one realistic '
        'room photograph, no collage, no labels. Scale is a visual estimate.'
    )
    task_id = str(uuid.uuid4())
    task = dict(taskType='imageInference', taskUUID=task_id,
                model='google:4@3', positivePrompt=prompt, numberResults=1,
                width=1200, height=896, outputType='base64Data', outputFormat='PNG',
                includeCost=True,
                inputs={'referenceImages': [data_uri(original), data_uri(sofa)]})
    key = os.environ.get('RUNWARE_API_KEY', '').strip() or (ROOT / 'runware_api_key.txt').read_text().strip()
    request = urllib.request.Request('https://api.runware.ai/v1',
        data=json.dumps([task]).encode(), headers={
            'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Runware returned HTTP {exc.code}. Check model access and credits.') from None
    if result.get('errors'):
        raise ValueError('; '.join(str(e.get('message', 'Generation failed')) for e in result['errors']).replace(key, '[REDACTED]')[:1000])
    row = next((r for r in result.get('data', []) if r.get('imageBase64Data')), None)
    if not row:
        raise ValueError('No image returned; no retry made. Task UUID: ' + task_id)
    output = ROOT / 'outputs' / ('sofa-inserted-' + task_id + '.png')
    Image.open(io.BytesIO(base64.b64decode(row['imageBase64Data'].split(',')[-1]))).save(output)
    metadata = dict(model=task['model'], taskUUID=task_id, room=str(room),
                    product=product, prompt=prompt, output=str(output), cost=row.get('cost'))
    output.with_suffix('.json').write_text(json.dumps(metadata, indent=2))
    return {'url': '/outputs/' + output.name, 'cost': row.get('cost'),
            'product_id': product['id'], 'product_name': product['name'],
            'room_url': state.get('empty_room') or state['room_candidate'],
            'placement': placement}
