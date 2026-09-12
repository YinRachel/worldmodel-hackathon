"""Local room-selection tool. Run: python3 select_room.py"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime
import json
import struct
from runware_edit import delete_object
from room_plan import PLAN
from workspace_state import read_state, update_state
from urllib.parse import urlparse, parse_qs
import threading
import uuid

JOBS = {}
JOB_LOCK = threading.Lock()
VIDEO_LOCK = threading.Lock()

def run_video(job_id, source_url, prompt, seconds):
    import asyncio
    import os
    from generate_room import generate_with_retries
    destination = ROOT / 'outputs' / ('furnished-video-' + job_id + '.mp4')
    def progress(message):
        JOBS[job_id] = {'status': 'running', 'message': message}
    try:
        key = os.environ.get('REACTOR_API_KEY', '').strip() or (ROOT / 'api_key.txt').read_text(encoding='utf-8-sig').strip()
        asyncio.run(generate_with_retries(ROOT / source_url.lstrip('/'), prompt, seconds, key, destination, progress))
        result = {'url': '/outputs/' + destination.name, 'source_url': source_url,
                  'prompt': prompt, 'seconds': seconds}
        update_state(video=result)
        JOBS[job_id] = {'status': 'complete', **result}
    except Exception:
        destination.unlink(missing_ok=True)
        JOBS[job_id] = {'status': 'failed', 'error': 'Helios could not finish this video. Check Reactor access, credits or capacity and try again.'}
    finally:
        VIDEO_LOCK.release()

def run_insert(job_id, state, placement):
    try:
        from runware_insert import insert_sofa
        result = insert_sofa(state, placement)
        update_state(insertion=result)
        JOBS[job_id] = {'status': 'complete', **result}
    except Exception:
        JOBS[job_id] = {'status': 'failed', 'error': 'Sofa insertion failed. Check your connection, Runware credits and product image availability. No automatic retry was made.'}
    finally:
        JOB_LOCK.release()

def run_clear(job_id, mask):
    try:
        name = delete_object(mask, clear_room=True)
        url = "/outputs/" + name
        update_state(room_candidate=url, empty_room=None)
        JOBS[job_id] = {"status":"complete", "url":url}
    except Exception as exc:
        JOBS[job_id] = {"status":"failed", "error":str(exc)[:1000]}
    finally:
        JOB_LOCK.release()

ROOT = Path(__file__).resolve().parent

class Handler(BaseHTTPRequestHandler):
    def respond(self, code, data, mime):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, data, code=200):
        self.respond(code, json.dumps(data).encode(), 'application/json')

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/plan':
            return self.json_response(PLAN)
        if parsed.path == '/state':
            return self.json_response(read_state())
        if parsed.path.startswith('/jobs/'):
            job = JOBS.get(parsed.path.split('/')[-1])
            return self.json_response(job or {'error':'Unknown job'}, 200 if job else 404)
        if parsed.path == '/catalog':
            from furniture_search import search_catalog
            try:
                return self.json_response(search_catalog(parse_qs(parsed.query).get('q',[''])[0]))
            except (ValueError, OSError):
                return self.json_response({'error':'Shopping search failed. Check your SerpApi connection and credits.'}, 502)
        routes = {'/': (ROOT / 'selection/index.html', 'text/html; charset=utf-8'),
                  '/room.jpeg': (ROOT / 'picture/IMG_9219.jpeg', 'image/jpeg')}
        if self.path == '/latest-mask':
            saved = read_state().get('mask_path')
            masks = [ROOT / saved] if saved else []
            if masks:
                self.respond(200, masks[-1].read_bytes(), 'image/png')
                return
        if self.path.startswith('/outputs/furnished-video-') and Path(self.path).name == self.path.removeprefix('/outputs/') and self.path.endswith('.mp4'):
            candidate = ROOT / 'outputs' / Path(self.path).name
            if candidate.is_file():
                return self.respond(200, candidate.read_bytes(), 'video/mp4')
        if self.path.startswith(('/outputs/runware-deleted-', '/outputs/sofa-inserted-', '/outputs/uploaded-room-')) and Path(self.path).name == self.path.removeprefix('/outputs/') and self.path.endswith('.png'):
            candidate = ROOT / 'outputs' / Path(self.path).name
            if candidate.is_file():
                self.respond(200, candidate.read_bytes(), 'image/png')
                return
        if self.path not in routes:
            self.respond(404, b'Not found', 'text/plain')
            return
        path, mime = routes[self.path]
        self.respond(200, path.read_bytes(), mime)

    def do_POST(self):
        try:
            if self.path not in ('/save-mask', '/delete', '/clear-room', '/choose-furniture', '/approve-room', '/insert-sofa', '/generate-video', '/upload-room', '/continue-cleaning'):
                raise ValueError('Unknown endpoint')
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                raise ValueError('Cross-origin request rejected')
            length = int(self.headers.get('Content-Length', '0'))
            if not 2 <= length <= 20_000_000:
                raise ValueError('Invalid mask size')
            data = self.rfile.read(length)
            if self.path == '/continue-cleaning':
                from PIL import Image
                if not JOB_LOCK.acquire(blocking=False):
                    return self.json_response({'error': 'Wait for the current image job to finish.'}, 409)
                try:
                    if VIDEO_LOCK.locked():
                        return self.json_response({'error': 'Wait for the video to finish.'}, 409)
                    state = read_state()
                    url = state.get('room_candidate')
                    if not url or not url.startswith('/outputs/runware-deleted-') or Path(url).name != url.removeprefix('/outputs/'):
                        raise ValueError('Generate a cleaning result first.')
                    with Image.open(ROOT / url.lstrip('/')) as image:
                        source = {'id': uuid.uuid4().hex, 'url': url, 'width': image.width, 'height': image.height}
                    return self.json_response(update_state(source_image=source, mask_path=None,
                        empty_room=None, insertion=None, insertion_job=None, video=None, video_job=None))
                finally:
                    JOB_LOCK.release()
            if self.path == '/upload-room':
                import io
                from PIL import Image, ImageOps
                if not JOB_LOCK.acquire(blocking=False):
                    return self.json_response({'error': 'Wait for the current image job before uploading.'}, 409)
                try:
                    if VIDEO_LOCK.locked():
                        return self.json_response({'error': 'Wait for the video to finish before uploading.'}, 409)
                    image = Image.open(io.BytesIO(data))
                    if image.width * image.height > 25_000_000:
                        raise ValueError('Choose an image smaller than 25 megapixels.')
                    image = ImageOps.exif_transpose(image).convert('RGB')
                    image_id = uuid.uuid4().hex
                    url = '/outputs/uploaded-room-' + image_id + '.png'
                    image.save(ROOT / url.lstrip('/'))
                    return self.json_response(update_state(source_image={'id': image_id, 'url': url, 'width': image.width, 'height': image.height}, mask_path=None, room_candidate=None, empty_room=None, insertion=None, insertion_job=None, video=None, video_job=None))
                finally:
                    JOB_LOCK.release()
            if self.path == '/generate-video':
                payload = json.loads(data)
                if not isinstance(payload, dict):
                    raise ValueError('Expected video settings.')
                prompt, seconds = payload.get('prompt'), payload.get('seconds')
                if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1500:
                    raise ValueError('Enter a motion prompt in 1–1500 characters.')
                if type(seconds) is not int or not 1 <= seconds <= 15:
                    raise ValueError('Choose a duration from 1 to 15 seconds.')
                source = (read_state().get('insertion') or {}).get('url', '')
                if not source.startswith('/outputs/sofa-inserted-') or Path(source).name != source.removeprefix('/outputs/') or not source.endswith('.png') or not (ROOT / source.lstrip('/')).is_file():
                    raise ValueError('Insert a sofa in step 3 before generating a video.')
                if not VIDEO_LOCK.acquire(blocking=False):
                    return self.json_response({'error': 'A Helios video is already running.'}, 409)
                job_id = uuid.uuid4().hex
                JOBS[job_id] = {'status': 'running', 'message': 'Starting Helios…'}
                update_state(video_job=job_id)
                threading.Thread(target=run_video, args=(job_id, source, prompt.strip(), seconds), daemon=True).start()
                return self.json_response({'job_id': job_id}, 202)
            if self.path == '/insert-sofa':
                state = read_state()
                payload = json.loads(data)
                placement = payload.get('placement') if isinstance(payload, dict) else None
                if not isinstance(placement, str) or not 1 <= len(placement.strip()) <= 1000:
                    raise ValueError('Describe the sofa placement in 1–1000 characters.')
                if not state.get('empty_room'):
                    raise ValueError('Click Use this room on your final cleaning result first.')
                if not (state.get('selected_product') or {}).get('image_url'):
                    raise ValueError('Choose a sofa with a product image first.')
                if not JOB_LOCK.acquire(blocking=False):
                    return self.json_response({'error': 'An image generation is already running.'}, 409)
                job_id = uuid.uuid4().hex
                JOBS[job_id] = {'status': 'running'}
                update_state(insertion_job=job_id)
                threading.Thread(target=run_insert, args=(job_id, state, placement.strip()), daemon=True).start()
                return self.json_response({'job_id': job_id}, 202)
            if self.path == '/choose-furniture':
                from furniture_search import get_product
                product_id = json.loads(data).get('id')
                product = get_product(product_id)
                if not product:
                    raise ValueError('Unknown catalog product')
                return self.json_response(update_state(selected_product=product))
            if self.path == '/approve-room':
                state=read_state()
                if not state.get('room_candidate'):
                    raise ValueError('Generate an empty room first')
                return self.json_response(update_state(empty_room=state['room_candidate']))
            if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
                raise ValueError('Expected a PNG mask')
            width, height = struct.unpack('>II', data[16:24])
            source = read_state().get('source_image')
            if not source or self.headers.get('X-Room-Id') != source['id']:
                raise ValueError('The room photo changed. Reload it before painting a new mask.')
            if (width, height) != (source['width'], source['height']):
                raise ValueError('Mask dimensions must match the uploaded room photo.')
            image_path = ROOT / source['url'].lstrip('/')
            if self.path == '/clear-room':
                raise ValueError('Use the brush to select furniture in your uploaded photo.')
            if self.path == '/delete':
                if not JOB_LOCK.acquire(blocking=False):
                    return self.json_response({'error': 'An image job is already running.'}, 409)
                try:
                    if read_state().get('source_image', {}).get('id') != source['id']:
                        raise ValueError('The room changed. Paint a new selection.')
                    name = delete_object(data, image_path=image_path)
                    update_state(room_candidate='/outputs/' + name, empty_room=None, insertion=None, insertion_job=None, video=None, video_job=None)
                finally:
                    JOB_LOCK.release()
                self.respond(200, json.dumps({'url': '/outputs/' + name}).encode(), 'application/json')
                return
            target = ROOT / 'outputs' / f'deletion-mask-{datetime.now():%Y%m%d-%H%M%S-%f}.png'
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(data)
            update_state(mask_path=str(target.relative_to(ROOT)))
            self.respond(200, json.dumps({'path': str(target)}).encode(), 'application/json')
        except (ValueError, OSError) as exc:
            self.respond(400, json.dumps({'error': str(exc)}).encode(), 'application/json')

if __name__ == '__main__':
    print('Open http://localhost:8000 — Ctrl+C to stop.', flush=True)
    try:
        ThreadingHTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
