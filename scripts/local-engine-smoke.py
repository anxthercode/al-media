"""Exercise the real Qt queue with bundled yt-dlp and FFmpeg, without site access."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from al_media.config import Preferences, app_root
from al_media.core.scheduler import Scheduler
from al_media.core.tools import bundled_tools
from al_media.database import Database
from al_media.models import State


def wait_for(predicate, timeout=60000):
    loop = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start(25)
    deadline.start(timeout)
    if not predicate():
        loop.exec()
    poll.stop()
    deadline.stop()
    if not predicate():
        raise RuntimeError("Timed out waiting for the real queue")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tools-root', type=Path)
    parser.add_argument('--url', help='Optional public media URL for an online smoke test')
    args = parser.parse_args()
    app = QCoreApplication([])
    tools = bundled_tools()
    if args.tools_root:
        tools = {name: args.tools_root / (name + '.exe') for name in tools}
    temp_root = app_root() / '.tmp'
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as temporary:
        root = Path(temporary)
        media = root / 'sample.mp4'
        subprocess.run([str(tools['ffmpeg']), '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=blue:s=128x72:r=25',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
                        '-t', '1', '-c:v', 'mpeg4', '-c:a', 'aac', str(media)],
                       capture_output=True, timeout=20, check=True)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        db = Database(root / 'queue.sqlite3')
        prefs = Preferences(folder=str(root / 'Мои видео'), concurrency=1)
        scheduler = Scheduler(db, tools, prefs)
        try:
            url = args.url or f'http://127.0.0.1:{server.server_port}/sample.mp4'
            for selection in ('best', 'mp3:192'):
                task = scheduler.add(url)
                wait_for(lambda task=task: task.state in {State.READY, State.FAILED} and not scheduler.jobs, 120000)
                if task.state != State.READY:
                    raise RuntimeError(f'Metadata failed: {task.error}')
                task.selection = selection
                scheduler.enqueue(task.id)
                wait_for(lambda task=task: task.state in {State.COMPLETED, State.FAILED} and not scheduler.jobs, 180000)
                if task.state != State.COMPLETED:
                    raise RuntimeError(f'Download failed: {task.error}')
                output = Path(task.final_path)
                assert output.is_file() and output.stat().st_size > 0
                result = subprocess.run([str(tools['ffprobe']), '-v', 'error', '-show_streams', '-of', 'json', str(output)],
                                        capture_output=True, text=True, encoding='utf-8', timeout=15, check=True)
                streams = json.loads(result.stdout)['streams']
                if selection.startswith('mp3:'):
                    assert any(stream['codec_name'] == 'mp3' for stream in streams)
                else:
                    assert any(stream['codec_type'] in {'video', 'audio'} for stream in streams)
                assert next(item for item in db.all() if item.id == task.id).state == State.COMPLETED
                print(f'Real queue: metadata -> {selection} -> final file -> ffprobe -> history: OK ({output.stat().st_size} bytes)')
        finally:
            scheduler.shutdown()
            for job in list(scheduler.jobs.values()):
                job.process.waitForFinished(3000)
            db.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    app.quit()


if __name__ == '__main__':
    main()

