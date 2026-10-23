"""Check real section downloads, image fidelity and Qt responsiveness locally."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic

from local_engine_smoke_helpers import wait_for
from PySide6.QtCore import QCoreApplication, QTimer

from al_media.config import Preferences, app_root
from al_media.core.scheduler import Scheduler
from al_media.core.tools import bundled_tools
from al_media.database import Database
from al_media.models import State, Task


class RangeHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, media, **kwargs):
        self.media = media
        super().__init__(*args, **kwargs)

    def do_GET(self):
        size = self.media.stat().st_size
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        start = min(size - 1, int(match[1])) if match else 0
        end = min(size - 1, int(match[2])) if match and match[2] else size - 1
        self.send_response(206 if match else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        if match:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default="1280x720", choices=("1280x720", "3840x2160"))
    options = parser.parse_args()
    width, height = map(int, options.size.split("x"))
    app = QCoreApplication([])
    root = app_root() / ".tmp/clip-quality"
    root.mkdir(parents=True, exist_ok=True)
    tools = bundled_tools()
    source = root / "source.mp4"
    subprocess.run([str(tools["ffmpeg"]), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc2=size={options.size}:rate=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                    "-t", "3", "-c:v", "mpeg4", "-q:v", "1", "-threads", "2", "-c:a", "aac", "-movflags", "+faststart", str(source)],
                   check=True, capture_output=True, timeout=30)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(RangeHandler, media=source))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    db = Database(root / "quality.sqlite3")
    scheduler = Scheduler(db, tools, Preferences(folder=str(root / "output")))
    task = Task(f"http://127.0.0.1:{server.server_port}/source.mp4", state=State.READY, duration=3,
                title="Quality check", folder=str(root / "output"), clip_start=.4, clip_end=1.6)
    scheduler.tasks[task.id] = task
    last, gaps = [monotonic()], []
    heartbeat = QTimer()
    heartbeat.setInterval(10)

    def tick():
        now = monotonic()
        gaps.append(now - last[0])
        last[0] = now

    heartbeat.timeout.connect(tick)
    heartbeat.start()
    try:
        scheduler.enqueue(task.id)
        wait_for(lambda: task.state in {State.COMPLETED, State.FAILED} and not scheduler.jobs)
        heartbeat.stop()
        if task.state != State.COMPLETED:
            raise RuntimeError(task.error)
        probe = subprocess.run([str(tools["ffprobe"]), "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration", "-of", "json", task.final_path],
                               check=True, capture_output=True, text=True, timeout=15)
        info = json.loads(probe.stdout)
        video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
        comparison = subprocess.run([str(tools["ffmpeg"]), "-hide_banner", "-i", str(source), "-i", task.final_path,
                                     "-filter_complex_threads", "2", "-filter_complex",
                                     "[0:v]trim=start=0.4:end=1.6,setpts=PTS-STARTPTS[ref];[1:v]setpts=PTS-STARTPTS[actual];[ref][actual]ssim",
                                     "-an", "-f", "null", "-"], capture_output=True, text=True, check=True, timeout=30)
        score = float(re.search(r"All:([0-9.]+)", comparison.stderr)[1])
        report = {"width": video["width"], "height": video["height"], "codec": video["codec_name"], "duration": float(info["format"]["duration"]),
                  "ssim": score, "max_qt_event_gap_ms": round(max(gaps) * 1000, 1), "file": task.final_path}
        (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        assert (video["width"], video["height"]) == (width, height)
        assert video["codec_name"] == "vp9" and 1.1 <= report["duration"] <= 1.35
        assert score >= .97, score
        assert report["max_qt_event_gap_ms"] < 500
    finally:
        heartbeat.stop()
        server.shutdown()
        db.close()
    app.quit()


if __name__ == "__main__":
    main()
