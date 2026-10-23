"""Exercise real asynchronous preview requests, sprite slicing and cache reuse."""
from __future__ import annotations

import os
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from local_engine_smoke_helpers import wait_for
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from al_media.config import app_root
from al_media.models import Task
from al_media.quick.media import MediaViewModel, PreviewProvider


class Handler(SimpleHTTPRequestHandler):
    requests = 0

    def do_GET(self):
        type(self).requests += 1
        super().do_GET()

    def log_message(self, *_):
        pass


def main():
    app = QApplication([])
    temporary_root = app_root() / ".tmp"
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="preview-smoke-", dir=temporary_root) as folder:
        root = Path(folder)
        sprite = QPixmap(3840, 1080)
        painter = QPainter(sprite)
        colors = [QColor(name) for name in ("red", "green", "blue", "yellow", "cyan", "magenta", "orange", "purple")]
        for index, color in enumerate(colors):
            painter.fillRect(index % 4 * 960, index // 4 * 540, 960, 540, color)
        painter.end()
        sprite.save(str(root / "sprite.png"))
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        provider = PreviewProvider()
        preview = MediaViewModel({}, provider)
        url = f"http://127.0.0.1:{server.server_port}/sprite.png"
        task = Task("https://example.test/video", thumbnail=url, duration=24,
                    formats=[{"protocol": "mhtml", "width": 960, "height": 540, "rows": 2, "columns": 4,
                              "fps": 1 / 3, "fragments": [{"url": url}]}])
        try:
            preview.set_task(task)
            wait_for(lambda: len(preview.frames) == 8, 10000)
            assert Handler.requests == 1, Handler.requests
            for index, color in enumerate(colors):
                assert preview.frames[index].toImage().pixelColor(20, 20) == color
            preview._advance()
            assert preview.source in ("image://preview/" + key for key in provider.images)
            assert preview.timer.interval() == 2400
            preview.setActive(False)
            assert not preview.timer.isActive()
            print("Qt Quick preview: 8 correct HTTP frames, one request, 2.4-second slideshow, pause when hidden: OK")
        finally:
            preview.shutdown()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    app.quit()


if __name__ == "__main__":
    main()
