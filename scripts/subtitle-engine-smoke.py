"""Exercise real subtitle download/conversion/muxing on local HTTP fixtures."""

from __future__ import annotations

import json
import subprocess
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from local_engine_smoke_helpers import wait_for
from PySide6.QtWidgets import QApplication

from al_media.config import Preferences, app_root
from al_media.core.engine import EngineJob
from al_media.core.metadata import populate_task
from al_media.core.naming import configure_destination
from al_media.core.tools import bundled_tools
from al_media.models import Task


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass


def main():
    app = QApplication([])
    tools = bundled_tools()
    base = app_root() / "build/qa"
    base.mkdir(parents=True, exist_ok=True)
    report = []
    with tempfile.TemporaryDirectory(prefix="subtitle-engine-", dir=base) as directory:
        root = Path(directory)
        subprocess.run([str(tools["ffmpeg"]), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=25",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "4", "-c:v", "mpeg4", "-q:v", "1",
                        "-threads", "2", "-c:a", "aac", "-movflags", "+faststart", str(root / "sample.mp4")],
                       capture_output=True, check=True, timeout=20)
        (root / "captions.vtt").write_text("WEBVTT\n\n00:00:00.500 --> 00:00:02.500\nПервая строка\n\n00:00:02.500 --> 00:00:04.000\nВторая строка\n", encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root)))
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            address = f"http://127.0.0.1:{server.server_port}"
            for name, clipping, automatic in (("full", False, False), ("clip", True, False), ("generated", False, True)):
                code = "en-orig" if automatic else "ru"
                info = {"id": name, "title": name, "extractor": "generic", "extractor_key": "Generic", "webpage_url": address + "/sample.mp4",
                        "duration": 4, "formats": [{"format_id": "http", "url": address + "/sample.mp4", "ext": "mp4", "protocol": "http",
                                                   "vcodec": "mpeg4", "acodec": "aac", "width": 640, "height": 360}],
                        "automatic_captions" if automatic else "subtitles": {code: [{"url": address + "/captions.vtt", "ext": "vtt"}]}}
                metadata = root / f"{name}.info.json"
                metadata.write_text(json.dumps(info), encoding="utf-8")
                folder = root / name
                folder.mkdir()
                task = Task(address + "/sample.mp4", folder=str(folder))
                populate_task(task, info)
                task.subtitle_language, task.subtitle_auto, task.subtitle_mode = code, automatic, "embedded"
                if clipping:
                    task.clip_start, task.clip_end = 1, 3
                preferences = Preferences(folder=str(folder))
                configure_destination(task, preferences)
                job = EngineJob(task, tools, preferences, "download")
                # Load deterministic source metadata; every actual media/subtitle
                # byte still goes through yt-dlp's HTTP download pipeline.
                job.process.setArguments([*job.process.arguments()[:-2], "--load-info-json", str(metadata)])
                files, failures, finished = [], [], []
                job.completed.connect(lambda _id, paths, target=files: target.extend(paths))
                job.failed.connect(lambda _id, error, target=failures: target.append(error))
                job.finished.connect(lambda _id, target=finished: target.append(True))
                job.start()
                wait_for(lambda target=finished: bool(target), timeout=90000)
                assert files and not failures, (name, failures, job.errors)
                output = Path(files[0])
                assert output.suffix == ".mkv"
                probe = subprocess.run([str(tools["ffprobe"]), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)],
                                       capture_output=True, check=True, text=True, encoding="utf-8", timeout=10)
                data = json.loads(probe.stdout)
                subtitles = [stream for stream in data["streams"] if stream["codec_type"] == "subtitle"]
                assert len(subtitles) == 1 and subtitles[0]["codec_name"] == "subrip"
                assert subtitles[0]["tags"]["language"] == ("eng" if automatic else "rus")
                assert {stream["codec_type"] for stream in data["streams"]} == {"video", "audio", "subtitle"}
                assert not any(path.suffix.lower() in {".srt", ".vtt", ".source"} for path in folder.iterdir())
                captions = subprocess.run([str(tools["ffmpeg"]), "-v", "error", "-i", str(output), "-map", "0:s:0", "-f", "srt", "-"],
                                          capture_output=True, check=True, text=True, encoding="utf-8", timeout=10).stdout
                assert "Первая строка" in captions and "Вторая строка" in captions
                if clipping:
                    assert "00:00:00,000 --> 00:00:01,500" in captions, captions
                    assert 1.8 < float(data["format"]["duration"]) < 2.5
                report.append({"case": name, "container": output.suffix, "subtitleLanguage": subtitles[0]["tags"]["language"],
                               "duration": data["format"]["duration"], "sidecars": False})
                job.deleteLater()
                app.processEvents()
                print(f"Real subtitle pipeline passed: {name}", flush=True)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
    (base / "subtitle-engine.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
