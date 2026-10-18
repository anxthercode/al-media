"""Verify downloads, codecs, cuts and captions using bundled tools and local HTTP."""
from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from local_engine_smoke_helpers import wait_for
from PySide6.QtCore import QCoreApplication

from al_media.config import Preferences, app_root
from al_media.core.scheduler import Scheduler
from al_media.core.tools import bundled_tools
from al_media.database import Database
from al_media.models import State


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def main():
    app = QCoreApplication([])
    tools = bundled_tools()
    temporary_root = app_root() / ".tmp"
    temporary_root.mkdir(exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="feature-smoke-", dir=temporary_root) as temporary:
        root = Path(temporary)
        def ffmpeg(*args):
            subprocess.run([str(tools["ffmpeg"]), "-hide_banner", "-loglevel", "error", "-y", *map(str, args)], capture_output=True, check=True, timeout=30)
        ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=160x90:r=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
               "-t", "6", "-c:v", "mpeg4", "-c:a", "aac", root / "sample.mp4")
        for rate in (128, 320):
            ffmpeg("-i", root / "sample.mp4", "-vn", "-c:a", "libmp3lame", "-b:a", f"{rate}k", root / f"native-{rate}.mp3")
        ffmpeg("-f", "lavfi", "-i", "color=c=teal:s=120x120", "-frames:v", "1", root / "cover.jpg")
        (root / "captions.vtt").write_text("WEBVTT\n\n00:00.500 --> 00:02.000\nFirst\n\n00:02.500 --> 00:05.000\nSecond\n", encoding="utf-8")
        (root / "index.html").write_text('<html><head><title>Media fixture</title></head><body><video controls poster="cover.jpg">'
                                         '<source src="sample.mp4" type="video/mp4"><track kind="subtitles" srclang="en" src="captions.vtt">'
                                         '</video></body></html>', encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        prefs = Preferences(folder=str(root / "Скачанные файлы"), concurrency=1)
        db = Database(root / "queue.sqlite3")
        scheduler = Scheduler(db, tools, prefs)
        def report_failure(task):
            if task.state == State.FAILED and task.id in scheduler.jobs:
                print("Local smoke engine stderr:", "\n".join(scheduler.jobs[task.id].errors[-12:]), flush=True)
        scheduler.changed.connect(report_failure)
        cases = [
            ("MP3 320 from video", "sample.mp4", "mp3:320", {}, 320000),
            ("Native MP3 128 preserved", "native-128.mp3", "mp3:320", {}, 128000),
            ("MP3 320 reduced to 128", "native-320.mp3", "mp3:128", {}, 128000),
            ("Precise video fragment", "sample.mp4", "best", {"clip_start": 1, "clip_end": 3.5}, None),
            ("Fragment with SRT", "index.html", "best", {"clip_start": 1, "clip_end": 3.5, "subtitle_language": "en", "subtitle_mode": "sidecar"}, None),
            ("Fragment with embedded subtitles", "index.html", "best", {"clip_start": 1, "clip_end": 3.5, "subtitle_language": "en", "subtitle_mode": "embedded"}, None),
            ("Music tags and cover", "index.html", "mp3:320", {}, 320000),
        ]
        try:
            for label, resource, selection, options, bitrate in cases:
                task = scheduler.add(f"http://127.0.0.1:{server.server_port}/{resource}")
                wait_for(lambda current=task: current.state in {State.READY, State.FAILED} and not scheduler.jobs, 60000)
                if task.state != State.READY:
                    raise RuntimeError(f"{label}: metadata: {task.error}")
                task.selection = selection
                for key, value in options.items():
                    setattr(task, key, value)
                scheduler.enqueue(task.id)
                wait_for(lambda current=task: current.state in {State.COMPLETED, State.FAILED} and not scheduler.jobs, 90000)
                if task.state != State.COMPLETED:
                    raise RuntimeError(f"{label}: download: {task.error}")
                probe = subprocess.run([str(tools["ffprobe"]), "-v", "error", "-show_streams", "-show_format", "-of", "json", task.final_path],
                                       capture_output=True, text=True, encoding="utf-8", check=True, timeout=20)
                info = json.loads(probe.stdout)
                if bitrate:
                    audio = next(stream for stream in info["streams"] if stream["codec_type"] == "audio")
                    assert audio["codec_name"] == "mp3", label
                    assert abs(int(audio["bit_rate"]) - bitrate) < 1000, (label, audio.get("bit_rate"))
                if "clip_end" in options:
                    assert abs(float(info["format"]["duration"]) - 2.5) < .25, (label, info["format"]["duration"])
                if options.get("subtitle_mode") == "sidecar":
                    subtitles = [path for path in Path(task.folder).iterdir() if path.name.startswith(Path(task.final_path).stem + ".") and path.suffix == ".srt"]
                    assert subtitles and "00:00:00,000 --> 00:00:01,000" in subtitles[0].read_text(encoding="utf-8"), label
                if options.get("subtitle_mode") == "embedded":
                    assert any(stream["codec_type"] == "subtitle" for stream in info["streams"]), label
                if label == "Music tags and cover":
                    assert any(stream.get("disposition", {}).get("attached_pic") for stream in info["streams"]), label
                    assert info["format"].get("tags", {}).get("title"), label
                results.append(label)
                print(label + ": OK", flush=True)
        finally:
            scheduler.shutdown()
            for job in list(scheduler.jobs.values()):
                job.process.waitForFinished(3000)
            db.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    print(f"Verified {len(results)} real media workflows")
    app.quit()


if __name__ == "__main__":
    main()
