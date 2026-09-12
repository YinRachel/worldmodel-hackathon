"""Generate a six-second room edit; run with .venv/bin/python generate_room.py."""
import argparse
import asyncio
from datetime import datetime
from fractions import Fraction
import os
from pathlib import Path

import av
from reactor_sdk import Reactor, RateLimitedError
from check_reactor import safe_error

ROOT = Path(__file__).resolve().parent
PROMPT = ('Fixed camera. Move the central green beanbag left, beside the other green '
          'beanbag. Keep the pool table, arcade machines, red stool, walls, lighting, '
          'and all other objects unchanged.')


async def generate(image, prompt, seconds, key, destination, progress=print):
    loop = asyncio.get_running_loop()
    frames = asyncio.Queue(maxsize=48)
    target = seconds * 24
    count = 0
    accepting = True
    container = None
    stream = None

    def enqueue(frame):
        if accepting and not frames.full():
            frames.put_nowait(frame)

    reactor = Reactor(model_name='reactor/helios', api_key=key,
                      max_session_duration_seconds=180)
    try:
        async with asyncio.timeout(150):
            progress('Connecting to Helios…')
            await reactor.connect()
            output = reactor.track('main_video')

            @output.on_frame
            def receive(frame):
                loop.call_soon_threadsafe(enqueue, frame.copy())

            progress('Uploading furnished room…')
            ref = await reactor.upload_file(image)
            reply = await reactor.send_command('set_conditioning', {'image': ref, 'prompt': prompt})
            if reply and reply.get('type') == 'command_error':
                raise RuntimeError(str(reply))
            await reactor.send_command('start', {})
            progress('Generating and recording…')
            while count < target:
                frame = await asyncio.wait_for(frames.get(), timeout=45)
                if container is None:
                    container = av.open(str(destination), mode='w', options={'movflags': '+faststart'})
                    stream = container.add_stream('libx264', rate=24)
                    stream.width = frame.shape[1]
                    stream.height = frame.shape[0]
                    stream.pix_fmt = 'yuv420p'
                    stream.options = {'preset': 'ultrafast', 'crf': '23'}
                video = av.VideoFrame.from_ndarray(frame, format='rgb24')
                video.pts = count
                video.time_base = Fraction(1, 24)
                for packet in stream.encode(video):
                    container.mux(packet)
                count += 1
                if count % 24 == 0:
                    progress(f'Recorded {count // 24}/{seconds} seconds')
    finally:
        accepting = False
        try:
            await asyncio.wait_for(reactor.disconnect(), timeout=15)
        finally:
            if container is not None:
                try:
                    for packet in stream.encode():
                        container.mux(packet)
                finally:
                    container.close()
    progress('Video ready.')


async def generate_with_retries(image, prompt, seconds, key, destination, progress=print):
    for attempt in range(4):
        try:
            return await generate(image, prompt, seconds, key, destination, progress)
        except RateLimitedError as exc:
            # Retry only an explicit capacity rejection during session creation.
            message = str(exc).lower()
            if ('create session' not in message or 'no available capacity' not in message
                    or destination.exists() or attempt == 3):
                raise
            delay = (15, 30, 45)[attempt]
            progress(f'Helios has no available servers. Retrying in {delay}s '
                  f'(attempt {attempt + 2}/4)...')
            await asyncio.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=ROOT / 'picture/IMG_9219.jpeg')
    parser.add_argument('--prompt', default=PROMPT)
    parser.add_argument('--seconds', type=int, choices=range(1, 16), default=6)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error('Room image does not exist.')
    key = os.environ.get('REACTOR_API_KEY', '').strip()
    if not key:
        key = (ROOT / 'api_key.txt').read_text(encoding='utf-8-sig').strip()
    destination = ROOT / 'outputs' / f'room-{datetime.now():%Y%m%d-%H%M%S-%f}.mp4'
    destination.parent.mkdir(exist_ok=True)
    try:
        asyncio.run(generate_with_retries(args.image, args.prompt, args.seconds, key, destination))
    except KeyboardInterrupt:
        raise SystemExit('Stopped. Any captured frames were saved.') from None
    except Exception as exc:
        detail = safe_error(str(exc), key) if key else str(exc)
        output_status = (f'A partial video was saved at {destination}'
                         if destination.exists() else 'No video was created.')
        raise SystemExit(f'Generation failed ({type(exc).__name__}): {detail}\n{output_status}') from None


if __name__ == '__main__':
    main()
