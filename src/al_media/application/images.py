from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QIODevice, QObject, QTimer, QUrl
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest


@dataclass(frozen=True)
class StoryboardFrame:
    url: str
    rect: tuple[int, int, int, int]


def storyboard_frames(task, count=8):
    supplied = [item for item in task.formats if item.get("protocol") == "mhtml" and item.get("fragments") and all(isinstance(item.get(key), (int, float)) and item[key] > 0 for key in ("width", "height", "rows", "columns"))]
    if not supplied:
        return []
    board = max(supplied, key=lambda item: item["width"] * item["height"])
    width, height, rows, columns = (int(board[key]) for key in ("width", "height", "rows", "columns"))
    fragments = board["fragments"]
    capacity = rows * columns
    total = capacity * len(fragments)
    if isinstance(board.get("fps"), (int, float)) and task.duration:
        total = min(total, max(1, round(board["fps"] * task.duration)))
    indices = sorted({min(total - 1, int(total * (index + 0.5) / min(count, total))) for index in range(min(count, total))})
    frames = []
    for index in indices:
        fragment = fragments[index // capacity]
        url = fragment.get("url", "") if isinstance(fragment, dict) else ""
        if url.startswith(("https://", "http://")):
            cell = index % capacity
            frames.append(StoryboardFrame(url, (cell % columns * width, cell // columns * height, width, height)))
    return frames


class ImageCache(QObject):
    """Bounded decoded-image cache and two asynchronous image requests at a time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.cache = OrderedDict()
        self.callbacks = {}
        self.pending = []
        self.active = 0
        self.bytes = 0
        self.closed = False

    def fetch(self, url, callback, low_priority=False):
        if self.closed or not url.startswith(("https://", "http://")):
            return
        if url in self.cache:
            self.cache.move_to_end(url)
            image = self.cache[url]
            QTimer.singleShot(0, lambda: callback(image))
            return
        if url in self.callbacks:
            self.callbacks[url].append(callback)
            return
        self.callbacks[url] = [callback]
        if low_priority:
            self.pending.append((url, low_priority))
        else:
            self.pending.insert(0, (url, low_priority))
        self._pump()

    def _pump(self):
        while not self.closed and self.active < 2 and self.pending:
            url, low = self.pending.pop(0)
            request = QNetworkRequest(QUrl(url))
            request.setTransferTimeout(10000)
            request.setPriority(QNetworkRequest.Priority.LowPriority if low else QNetworkRequest.Priority.NormalPriority)
            reply = self.network.get(request)
            self.active += 1
            reply.downloadProgress.connect(lambda received, _total, current=reply: current.abort() if received > 12_000_000 else None)
            reply.finished.connect(lambda current=reply, key=url: self._finished(key, current))

    def _finished(self, url, reply):
        pixmap = QPixmap()
        if reply.error() == reply.NetworkError.NoError:
            data = reply.readAll()
            buffer = QBuffer()
            buffer.setData(data)
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            reader = QImageReader(buffer)
            reader.setAutoTransform(True)
            size = reader.size()
            if len(data) <= 12_000_000 and 0 < size.width() * size.height() <= 16_000_000:
                pixmap = QPixmap.fromImage(reader.read())
        if not pixmap.isNull():
            self.cache[url] = pixmap
            self.bytes += pixmap.width() * pixmap.height() * 4
            while self.bytes > 64_000_000 and len(self.cache) > 1:
                _, removed = self.cache.popitem(last=False)
                self.bytes -= removed.width() * removed.height() * 4
        callbacks = self.callbacks.pop(url, [])
        self.active -= 1
        reply.deleteLater()
        for callback in callbacks:
            callback(pixmap)
        self._pump()

    def shutdown(self):
        from PySide6.QtNetwork import QNetworkReply

        self.closed = True
        self.pending.clear()
        self.callbacks.clear()
        for reply in self.network.findChildren(QNetworkReply):
            reply.abort()
