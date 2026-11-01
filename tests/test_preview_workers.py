"""Cold preview/probe launches must not block mode buttons or leak stale output."""

from __future__ import annotations

import json
import sys
from threading import Event
from time import monotonic, sleep

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QSignalSpy

from al_media.core import preview_frames, process_runner, source_probe
from al_media.models import Task


def slow_launcher(monkeypatch):
    original = process_runner.subprocess.Popen
    entered = Event()

    def launch(*args, **kwargs):
        entered.set()
        sleep(0.35)  # Model the cold Windows tool startup, before a PID exists.
        return original(*args, **kwargs)

    monkeypatch.setattr(process_runner.subprocess, "Popen", launch)
    return entered


def test_preview_launch_is_async_binary_output_is_clean_and_cancel_retires_worker(qapp, qtbot, tmp_path, monkeypatch):
    entered = slow_launcher(monkeypatch)
    poster = tmp_path / "frame.jpg"
    image = QPixmap(640, 360)
    image.fill(QColor("blue"))
    assert image.save(str(poster), "JPEG")
    local = tmp_path / "local.mp4"
    local.write_bytes(b"fixture")
    code = "import pathlib,sys; sys.stderr.write('diagnostic'); sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())"
    monkeypatch.setattr(preview_frames, "ProcessRunner", lambda args, channel, parent, **kw:
                        process_runner.ProcessRunner([sys.executable, "-c", code, str(poster)], channel, parent, **kw))
    extractor = preview_frames.FrameExtractor("ffmpeg", None)
    frames, ticks = [], []
    extractor.ready.connect(lambda index, frame: frames.append((index, frame.size())))
    heartbeat = QTimer(interval=10)
    heartbeat.timeout.connect(lambda: ticks.append(monotonic()))
    heartbeat.start()
    try:
        extractor.set_task(Task("https://example.test/preview", duration=60, final_path=str(local)))
        start = monotonic()
        extractor.set_enabled(True)
        assert monotonic() - start < 0.15
        qtbot.waitUntil(entered.is_set)
        qtbot.waitUntil(lambda: bool(frames), timeout=5000)
        extractor.set_enabled(False)
        qtbot.waitUntil(lambda: not extractor.busy, timeout=5000)
        assert frames[0][1].width() == 640 and frames[0][1].height() == 360
        assert max(b - a for a, b in zip(ticks, ticks[1:], strict=False)) < 0.25
        # A second cold launch is cancelled while CreateProcess is still pending.
        entered.clear()
        extractor.set_enabled(True)
        qtbot.waitUntil(entered.is_set)
        extractor.set_task(None)
        count = len(frames)
        assert extractor.busy
        qtbot.waitUntil(lambda: not extractor.busy, timeout=5000)
        assert len(frames) == count and extractor.process is None
        entered.clear()
        cancelled = process_runner.ProcessRunner([sys.executable, "-c", "pass"], "out", extractor)
        retired = QSignalSpy(cancelled.finished)
        cancelled.cancel()
        cancelled.start()
        qtbot.waitUntil(lambda: retired.count() == 1)
        cancelled.wait()
        assert not entered.is_set()  # A cancelled pending preview never launches.
    finally:
        heartbeat.stop()
        extractor.shutdown()
        qtbot.waitUntil(lambda: not extractor.busy, timeout=5000)


def test_source_probe_cold_launch_ignores_cancelled_source_and_updates_current(qapp, qtbot, tmp_path, monkeypatch):
    entered = slow_launcher(monkeypatch)
    info = json.dumps({"format": {"duration": "16", "size": "100000", "bit_rate": "50000"}})
    code = "import sys; sys.stderr.write('diagnostic'); print(sys.argv[1])"
    monkeypatch.setattr(source_probe, "ProcessRunner", lambda args, channel, parent, **kw:
                        process_runner.ProcessRunner([sys.executable, "-c", code, info], channel, parent, **kw))
    probe = source_probe.SourceProbe(tmp_path / "ffprobe.exe")
    probe.executable.write_bytes(b"fixture")
    old = Task("https://example.test/old", formats=[{"url": "https://example.test/old.mp4", "ext": "mp4"}])
    current = Task("https://example.test/current", formats=[{"url": "https://example.test/current.mp4", "ext": "mp4"}])
    updates = []
    probe.updated.connect(updates.append)
    try:
        start = monotonic()
        probe.start(old)
        assert monotonic() - start < 0.15
        qtbot.waitUntil(entered.is_set)
        probe.start(current)
        qtbot.waitUntil(lambda: not probe.busy, timeout=5000)
        assert old.duration is None and updates == [current]
        assert current.duration == 16 and current.formats[0]["filesize"] == 100000
    finally:
        probe.shutdown()
        qtbot.waitUntil(lambda: not probe.busy, timeout=5000)
