"""Run the Qt Quick composer through real local yt-dlp/FFmpeg downloads."""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from al_media.config import Preferences, app_root
from al_media.core.scheduler import Scheduler
from al_media.core.tools import bundled_tools
from al_media.database import Database
from al_media.models import State
from al_media.quick.bootstrap import QuickApplication


def wait_for(predicate, timeout=40):
    deadline = monotonic() + timeout
    while not predicate() and monotonic() < deadline:
        QTest.qWait(20)
    assert predicate(), "Timed out waiting for the native download workflow"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # Probes intentionally stop reading when they have enough data.


def main():
    app = QApplication([])
    tools = bundled_tools()
    base = app_root() / "build/qa"
    base.mkdir(parents=True, exist_ok=True)
    report_path = base / "quick-engine.json"
    with tempfile.TemporaryDirectory(prefix="quick-engine-", dir=base) as directory:
        root = Path(directory)
        source = root / "sample.mp4"
        subprocess.run(
            [
                str(tools["ffmpeg"]),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=640x360:r=25",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100",
                "-t",
                "4",
                "-c:v",
                "mpeg4",
                "-q:v",
                "1",
                "-threads",
                "2",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(source),
            ],
            capture_output=True,
            check=True,
            timeout=20,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        database = Database(root / "queue.sqlite3")
        scheduler = Scheduler(database, tools, Preferences(folder=str(root / "Мои видео"), concurrency=2))
        presentation = QuickApplication(app, scheduler, scheduler.preferences, isolated=True)
        presentation.window.show()
        # Settle the first native frame / driver initialization before measuring
        # interaction latency; normal users paste a URL into an already drawn UI.
        QTest.qWait(500)
        composer = presentation.controller.composer
        diagnostics = []
        factory = composer.job_factory

        def make_job(*args):
            job = factory(*args)
            job.failed.connect(lambda *_: diagnostics.extend(job.errors))
            return job

        composer.job_factory = make_job
        ticks, transitions = [], []
        heartbeat = QTimer(interval=20)
        heartbeat.timeout.connect(lambda: ticks.append(monotonic()))
        heartbeat.start()
        scheduler.changed.connect(lambda task: transitions.append(task.state.value))
        try:
            composer.setUrl(f"http://127.0.0.1:{server.server_port}/sample.mp4")
            composer.analyze()
            wait_for(lambda: composer.state["phase"] in {"ready", "error"})
            assert composer.state["phase"] == "ready", (composer.state["error"], diagnostics)
            composer.editRange("clip", True)
            composer.editRange("start", "0:01")
            composer.editRange("end", "0:03")
            assert composer.applyRange()
            composer.download()
            composer.setMode("audio")
            composer.select("mp3:192")
            composer.download()
            wait_for(lambda: len(scheduler.tasks) == 2 and all(t.state in {State.COMPLETED, State.FAILED} for t in scheduler.tasks.values()))
            wait_for(lambda: not scheduler.jobs)
            heartbeat.stop()
            output = []
            for task in scheduler.tasks.values():
                assert task.state == State.COMPLETED, task.error
                assert Path(task.final_path).is_file()
                details = subprocess.run(
                    [str(tools["ffprobe"]), "-v", "error", "-show_entries", "format=duration,bit_rate:stream=codec_name,width,height", "-of", "json", task.final_path], capture_output=True, check=True, text=True, timeout=10
                )
                info = json.loads(details.stdout)
                assert 1.8 < float(info["format"]["duration"]) < 2.4
                if task.selection.startswith("mp3:"):
                    assert info["streams"][0]["codec_name"] == "mp3"
                else:
                    video = next(stream for stream in info["streams"] if stream.get("width"))
                    assert video["width"] == 640 and video["height"] == 360
                output.append({"selection": task.selection, "clip": [task.clip_start, task.clip_end], "probe": info})
            gaps = [b - a for a, b in zip(ticks, ticks[1:], strict=False)]
            assert max(gaps, default=0) < 1, "GUI event loop blocked for a second"
            assert not presentation.warnings
            report_path.write_text(
                json.dumps({"platform": app.platformName(), "heartbeatMaxMs": round(max(gaps, default=0) * 1000, 2), "stateTransitions": sorted(set(transitions)), "files": output}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("Native Qt Quick / composer / scheduler / yt-dlp / FFmpeg: two real local clips passed")
        finally:
            heartbeat.stop()
            presentation.controller.quit()
            wait_for(lambda: presentation.controller._exit_ready)
            presentation.window.hide()
            presentation.dispose()
            QTest.qWait(100)
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
            database.close()


if __name__ == "__main__":
    main()
