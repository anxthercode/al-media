"""Verify real FFmpeg preview seeks, cancellation, cache reuse and HTTP fallback."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from local_engine_smoke_helpers import wait_for
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from al_media.config import app_root
from al_media.core.tools import bundled_tools
from al_media.models import Task
from al_media.ui.preview_frames import FrameExtractor


class RangeHandler(BaseHTTPRequestHandler):
    requests = []

    def __init__(self, *args, media, **kwargs):
        self.media = media
        super().__init__(*args, **kwargs)

    def do_GET(self):
        header = self.headers.get("Range", "")
        type(self).requests.append((self.path, header))
        size = self.media.stat().st_size
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", header) if self.path == "/seek.mp4" else None
        start = min(size - 1, int(match[1])) if match else 0
        end = min(size - 1, int(match[2])) if match and match[2] else size - 1
        self.send_response(206 if match else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(end - start + 1))
        if match:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        try:
            with self.media.open("rb") as source:
                source.seek(start)
                remaining = end - start + 1
                while remaining:
                    data = source.read(min(16384, remaining))
                    self.wfile.write(data)
                    remaining -= len(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *_):
        pass


def main():
    app = QApplication([])
    ffmpeg = bundled_tools()["ffmpeg"]
    with tempfile.TemporaryDirectory(prefix="frame-smoke-", dir=app_root() / ".tmp") as folder:
        media = Path(folder) / "video.mp4"
        subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=1280x720:rate=12:duration=8", "-an", "-c:v", "mpeg4", "-q:v", "3",
                        "-threads", "1", "-g", "12", "-movflags", "+faststart", str(media)], check=True, timeout=45)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(RangeHandler, media=media))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        extractor = FrameExtractor(ffmpeg)
        base = f"http://127.0.0.1:{server.server_port}"
        task = Task(base + "/source", duration=8, formats=[{"url": base + "/seek.mp4", "vcodec": "h264", "height": 720}])
        frames = {}
        paused = False

        def ready(index, image):
            nonlocal paused
            frames[index] = image
            if not paused:
                paused = True
                extractor.set_enabled(False)

        extractor.ready.connect(ready)
        try:
            extractor.set_task(task)
            extractor.set_enabled(True)
            wait_for(lambda: len(frames) == 1, 20000)
            QTest.qWait(250)
            assert len(frames) == 1 and extractor.process is None
            extractor.set_enabled(True)
            wait_for(lambda: len(frames) == 8, 45000)
            assert all((image.width(), image.height()) == (1280, 720) for image in frames.values())
            assert RangeHandler.requests[0] == ("/seek.mp4", "bytes=0-0")
            assert all(header.startswith("bytes=") for _path, header in RangeHandler.requests)
            requests = len(RangeHandler.requests)
            extractor.set_task(None)
            frames.clear()
            extractor.set_task(task)
            QTest.qWait(200)
            assert len(frames) == 8 and len(RangeHandler.requests) == requests
            print("Real ranged HTTP video: eight 1280x720 frames, pause/resume, input seeks and cache reuse: OK")
            frames.clear()
            extractor.set_task(Task(base + "/unsupported", duration=8, formats=[{"url": base + "/no-seek.mp4", "vcodec": "h264", "height": 720}]))
            wait_for(lambda: extractor.probed, 10000)
            QTest.qWait(200)
            assert not extractor.seekable and not frames and extractor.process is None
            assert RangeHandler.requests[requests:] == [("/no-seek.mp4", "bytes=0-0")]
            print("Server ignores ranges: one probe, no FFmpeg scan, poster fallback: OK")
        finally:
            extractor.shutdown()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    app.quit()


if __name__ == "__main__":
    main()
