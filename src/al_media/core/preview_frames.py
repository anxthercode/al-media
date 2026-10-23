from __future__ import annotations

import math
import re
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest


def preview_source(task):
    """Use a seekable local file or a modest direct video stream, never a playlist."""
    if not task or task.playlist or not task.duration or not math.isfinite(task.duration) or task.duration <= 0:
        return None
    if task.final_path:
        path = Path(task.final_path)
        if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"} and path.is_file():
            duration = max(0, (task.clip_end or task.duration) - (task.clip_start or 0))
            return str(path.resolve()), {}, 0, duration
    formats = [item for item in task.formats if item.get("vcodec") not in (None, "none")
               and item.get("protocol") in (None, "http", "https") and not item.get("has_drm")
               and not item.get("fragments") and str(item.get("url", "")).startswith(("https://", "http://"))
               and isinstance(item.get("height"), (int, float)) and item["height"] > 0]
    if not formats:
        return None
    stream = min(formats, key=lambda item: (item["height"] < 720, abs(item["height"] - 720),
                                           not str(item.get("vcodec", "")).startswith(("avc", "h264"))))
    headers = stream.get("http_headers") if isinstance(stream.get("http_headers"), dict) else {}
    headers = {key: value for key, value in headers.items() if isinstance(key, str) and isinstance(value, str)
               and re.fullmatch(r"[A-Za-z0-9-]+", key) and "\r" not in value and "\n" not in value
               and key.lower() not in {"range", "content-length", "host", "connection"}}
    start, end = task.clip_start or 0, task.clip_end or task.duration
    return stream["url"], headers, start, max(0, end - start)


class FrameExtractor(QObject):
    """One cancellable FFmpeg seek at a time, with a bounded in-memory frame cache.

    Remote previews require a successful one-byte HTTP range request. Servers
    without seeking retain their poster instead of downloading a video to scan it.
    """

    ready = Signal(int, QPixmap)

    def __init__(self, ffmpeg, parent=None):
        super().__init__(parent)
        self.ffmpeg = str(ffmpeg)
        self.network = QNetworkAccessManager(self)
        self.source = self.key = None
        self.process = self.reply = None
        self.frames = OrderedDict()
        self.bytes = 0
        self.index = self.failures = 0
        self.enabled = self.seekable = False
        self.probed = False
        self.buffer = bytearray()
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timeout)

    def set_task(self, task):
        source = preview_source(task)
        key = (task.url, task.clip_start, task.clip_end, source[0] if source and not source[0].startswith(("https://", "http://")) else "") if task else None
        if key == self.key and source == self.source:
            return
        self._stop()
        self.source, self.key = source, key
        self.index = self.failures = 0
        self.seekable = bool(source and not source[0].startswith(("https://", "http://")))
        self.probed = self.seekable
        cached = self.frames.get(key, {})
        if cached:
            self.frames.move_to_end(key)
            for index, image in cached.items():
                self.ready.emit(index, image)
            self.index = max(cached) + 1
        self._pump()

    def set_enabled(self, enabled):
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self._pump()
        else:
            self._stop()

    def _pump(self):
        if not self.enabled or not self.source or self.process or self.reply or self.index >= 8 or self.failures >= 2:
            return
        if not self.probed:
            self._probe()
            return
        if not self.seekable:
            return
        url, headers, start, duration = self.source
        if duration <= 0:
            return
        arguments = ["-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "1"]
        if url.startswith(("http://", "https://")):
            arguments += ["-rw_timeout", "5000000", "-seekable", "1"]
            if headers:
                arguments += ["-headers", "".join(f"{key}: {value}\r\n" for key, value in headers.items())]
        # Input seeking uses the index/ranges; output seeking would scan the file.
        arguments += ["-ss", f"{start + duration * (self.index + .5) / 8:.3f}", "-i", url,
                      "-map", "0:v:0", "-an", "-sn", "-dn", "-frames:v", "1", "-filter_threads", "1",
                      "-vf", "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease",
                      "-threads", "1", "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "2", "pipe:1"]
        process = QProcess(self)
        self.process = process
        self.buffer.clear()
        process.setProgram(self.ffmpeg)
        process.setArguments(arguments)
        process.readyReadStandardOutput.connect(lambda: self._read(process))
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.finished.connect(lambda code, _status: self._finished(process, code))
        process.errorOccurred.connect(lambda error: self._finished(process, -1) if error == QProcess.ProcessError.FailedToStart else None)
        self.timeout.start(10000)
        process.start()

    def _probe(self):
        url, headers, *_ = self.source
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(6000)
        for key, value in headers.items():
            request.setRawHeader(key.encode("ascii"), value.encode("utf-8"))
        request.setRawHeader(b"Range", b"bytes=0-0")
        request.setPriority(QNetworkRequest.Priority.LowPriority)
        reply = self.network.get(request)
        self.reply = reply
        reply.metaDataChanged.connect(lambda: reply.abort() if reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) == 200 else None)
        reply.readyRead.connect(lambda: reply.abort() if reply.bytesAvailable() > 4096 else None)
        reply.finished.connect(lambda: self._probe_finished(reply))
        self.timeout.start(7000)

    def _probe_finished(self, reply):
        if reply is self.reply:
            self.timeout.stop()
            self.reply = None
            self.probed = True
            self.seekable = (reply.error() == reply.NetworkError.NoError
                             and reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) == 206
                             and bool(re.fullmatch(rb"bytes 0-0/[1-9][0-9]*", bytes(reply.rawHeader("Content-Range")))))
            QTimer.singleShot(0, self._pump)
        reply.deleteLater()

    def _read(self, process):
        data = bytes(process.readAllStandardOutput())
        if process is self.process:
            self.buffer.extend(data)
            if len(self.buffer) > 4_000_000:
                self.buffer.clear()
                process.kill()

    def _finished(self, process, code):
        if process is self.process:
            self.timeout.stop()
            self._read(process)
            self.process = None
            image = QPixmap()
            if code == 0 and self.buffer:
                image.loadFromData(bytes(self.buffer), "JPEG")
            self.buffer.clear()
            index = self.index
            self.index += 1
            if not image.isNull():
                self.failures = 0
                self.frames.setdefault(self.key, {})[index] = image
                self.frames.move_to_end(self.key)
                self.bytes += image.width() * image.height() * 4
                while self.bytes > 32_000_000 and len(self.frames) > 1:
                    _, images = self.frames.popitem(last=False)
                    self.bytes -= sum(frame.width() * frame.height() * 4 for frame in images.values())
                self.ready.emit(index, image)
            else:
                self.failures += 1
            QTimer.singleShot(100, self._pump)
        process.deleteLater()

    def _timeout(self):
        if self.reply:
            self.reply.abort()
        if self.process:
            self.process.kill()

    def _stop(self, wait=False):
        self.timeout.stop()
        reply, self.reply = self.reply, None
        if reply:
            reply.abort()
        process, self.process = self.process, None
        if process:
            process.kill()
            if wait:
                process.waitForFinished(500)
        self.buffer.clear()

    def shutdown(self):
        self.enabled = False
        self._stop(wait=True)
