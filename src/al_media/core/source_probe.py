from __future__ import annotations

import json
import math
import re

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from .metadata import estimate_size
from .process_runner import ProcessRunner


def positive_number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def probe_candidates(task):
    direct = [item for item in task.formats if str(item.get("url", "")).startswith(("https://", "http://"))
              and item.get("protocol") in (None, "http", "https") and not item.get("fragments") and not item.get("has_drm")]
    audio = [item for item in direct if item.get("vcodec") == "none" and item.get("acodec") not in (None, "none")]
    video = [item for item in direct if item.get("vcodec") not in (None, "none") or item.get("ext") in {"mp4", "webm", "mov"}]
    audio.sort(key=lambda item: item.get("abr") or item.get("tbr") or 0)
    video.sort(key=lambda item: (abs((item.get("height") or 720) - 720), item.get("tbr") or 0))
    return audio[:1] + video[:1]


def probe_arguments(stream):
    args = ["-v", "error", "-rw_timeout", "5000000", "-probesize", "1000000", "-analyzeduration", "1000000"]
    supplied = stream.get("http_headers")
    headers = {key: value for key, value in (supplied.items() if isinstance(supplied, dict) else [])
               if isinstance(key, str) and isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9-]+", key)
               and "\r" not in value and "\n" not in value and key.lower() not in {"range", "host", "content-length", "connection"}}
    if headers:
        args += ["-headers", "".join(f"{key}: {value}\r\n" for key, value in headers.items())]
    return [*args, "-show_entries", "format=duration,size,bit_rate:stream=duration,bit_rate", "-of", "json", "-i", stream["url"]]


def apply_probe(task, stream, info):
    container = info.get("format") if isinstance(info.get("format"), dict) else {}
    streams = info.get("streams") if isinstance(info.get("streams"), list) else []
    duration = positive_number(container.get("duration")) or max(
        (positive_number(item.get("duration")) or 0 for item in streams if isinstance(item, dict)), default=0)
    if task.duration is None and duration:
        task.duration = duration
    size = positive_number(container.get("size"))
    if size:
        stream["filesize"] = int(size)
    bitrate = positive_number(container.get("bit_rate"))
    if bitrate and not positive_number(stream.get("tbr")):
        stream["tbr"] = bitrate / 1000
    task.estimated_size = estimate_size(task)


class SourceProbe(QObject):
    """Fill missing source facts asynchronously from at most two direct streams."""

    updated = Signal(object)

    def __init__(self, executable, parent=None):
        super().__init__(parent)
        self.executable = executable
        self.process = self.task = self.stream = None
        self.runners = set()
        self.pending = []
        self.output = bytearray()
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timed_out)

    def start(self, task):
        self.cancel()
        if not self.executable or not self.executable.is_file() or task.playlist or task.duration and estimate_size(task):
            return
        self.task = task
        self.pending = probe_candidates(task)
        self._next()

    def cancel(self):
        self.timeout.stop()
        process, self.process = self.process, None
        self.task = None
        self.pending = []
        if process:
            process.cancel()

    def _next(self):
        if not self.pending or not self.task:
            return
        self.stream = self.pending.pop(0)
        self.output.clear()
        process = ProcessRunner([str(self.executable), *probe_arguments(self.stream)], "out", self, discard_stderr=True)
        self.process = process
        self.runners.add(process)
        process.output.connect(self._read, Qt.ConnectionType.QueuedConnection)
        process.finished.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        self.timeout.start(10000)
        process.start()

    @Slot(str, bytes)
    def _read(self, _channel, data):
        process = self.sender()
        if process is self.process:
            self.output.extend(data)
            if len(self.output) > 128000:
                process.cancel()

    def _timed_out(self):
        if self.process:
            self.process.cancel()

    @Slot(int)
    def _finished(self, code):
        process = self.sender()
        self.runners.discard(process)
        if process is not self.process:
            process.deleteLater()
            return
        self.timeout.stop()
        self.process = None
        if code == 0:
            try:
                info = json.loads(self.output)
                if isinstance(info, dict):
                    apply_probe(self.task, self.stream, info)
                    self.updated.emit(self.task)
            except (ValueError, TypeError):
                pass
        process.deleteLater()
        if self.task and (self.task.duration is None or estimate_size(self.task) is None):
            self._next()

    def shutdown(self):
        self.cancel()

    @property
    def busy(self):
        return bool(self.runners)
