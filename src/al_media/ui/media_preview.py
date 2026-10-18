from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QIODevice, QObject, QRect, QRectF, QSize, Qt, QTimer, QUrl, QVariantAnimation
from PySide6.QtGui import QColor, QImageReader, QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import QBoxLayout, QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene, QSizePolicy, QWidget
from shiboken6 import isValid

from al_media.core.metadata import selection_kind

from .preview_frames import FrameExtractor
from .themes import palette


def blurred_backdrop(pixmap, size):
    """Blur the entire frame at a bounded resolution, without a cover crop."""
    canvas = size.scaled(QSize(800, 400), Qt.AspectRatioMode.KeepAspectRatio) if size.width() > 800 or size.height() > 400 else size
    source = pixmap.scaled(canvas, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    # Extend edge pixels so blur does not introduce a dark/transparent rim.
    pad, width, height = 48, canvas.width(), canvas.height()
    padded = QPixmap(width + pad * 2, height + pad * 2)
    padded.fill(Qt.GlobalColor.transparent)
    edges = QPainter(padded)
    edges.drawPixmap(pad, pad, source)
    for target, origin in ((QRect(pad, 0, width, pad), QRect(0, 0, width, 1)),
                           (QRect(pad, pad + height, width, pad), QRect(0, height - 1, width, 1)),
                           (QRect(0, pad, pad, height), QRect(0, 0, 1, height)),
                           (QRect(pad + width, pad, pad, height), QRect(width - 1, 0, 1, height))):
        edges.drawPixmap(target, source, origin)
    corners = source.toImage()
    for x, y, sx, sy in ((0, 0, 0, 0), (pad + width, 0, width - 1, 0),
                         (0, pad + height, 0, height - 1), (pad + width, pad + height, width - 1, height - 1)):
        edges.fillRect(x, y, pad, pad, corners.pixelColor(sx, sy))
    edges.end()
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(padded)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(18)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    result = QPixmap(canvas)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    scene.render(painter, QRectF(result.rect()), QRectF(pad, pad, width, height))
    painter.end()
    return result


@dataclass(frozen=True)
class StoryboardFrame:
    url: str
    rect: tuple[int, int, int, int]


def storyboard_frames(task, count=8):
    supplied = [item for item in task.formats if item.get("protocol") == "mhtml" and item.get("fragments")
                and all(isinstance(item.get(key), (int, float)) and item[key] > 0 for key in ("width", "height", "rows", "columns"))]
    if not supplied:
        return []
    board = max(supplied, key=lambda item: item["width"] * item["height"])
    width, height, rows, columns = (int(board[key]) for key in ("width", "height", "rows", "columns"))
    fragments = board["fragments"]
    capacity = rows * columns
    total = capacity * len(fragments)
    if isinstance(board.get("fps"), (int, float)) and task.duration:
        total = min(total, max(1, round(board["fps"] * task.duration)))
    indices = sorted({min(total - 1, int(total * (index + .5) / min(count, total))) for index in range(min(count, total))})
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

    def fetch(self, url, callback, low_priority=False):
        if not url.startswith(("https://", "http://")):
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
        while self.active < 2 and self.pending:
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


class MediaPreview(QWidget):
    def __init__(self, cache, preferences, icon, parent=None, *, tools=None):
        super().__init__(parent)
        self.cache, self.preferences, self.icon = cache, preferences, icon
        self.key = None
        self.cover = QPixmap()
        self.current = QPixmap()
        self.previous = QPixmap()
        self.backdrops = OrderedDict()
        self.frames = {}
        self.index = -1
        self.video = False
        self.fade = 1.0
        self.setMinimumSize(220, 180)
        self.setMaximumHeight(260)
        self.setMaximumWidth(16777215)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.advance)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(300)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.valueChanged.connect(self._fade_changed)
        self.extractor = FrameExtractor(tools["ffmpeg"], self) if tools and tools.get("ffmpeg") and tools["ffmpeg"].is_file() else None
        if self.extractor:
            self.extractor.ready.connect(self._sharp_frame_ready)

    def heightForWidth(self, width):
        width = min(width, self.maximumWidth())
        return min(260, max(180, round(width * 9 / 16)))

    def sizeHint(self):
        return QSize(430, self.heightForWidth(430))

    def set_task(self, task):
        video = bool(task and selection_kind(task.selection) == "video")
        key = (task.id, task.thumbnail, video, task.clip_start, task.clip_end) if task else None
        if self.key == key:
            if self.extractor:
                self.extractor.set_task(task if video else None)
            self.sync_animation()
            return
        retained_cover = self.cover if self.key and key and self.key[:2] == key[:2] else QPixmap()
        self.key, self.video = key, video
        self.timer.stop()
        self.animation.stop()
        self.frames.clear()
        self.cover = self.current = retained_cover
        self.previous = QPixmap()
        self.backdrops.clear()
        self.fade, self.index = 1.0, -1
        self.updateGeometry()
        self.update()
        if self.extractor:
            self.extractor.set_task(task if video else None)
        if not task:
            return
        candidates = list(dict.fromkeys([task.thumbnail, *task.thumbnail_candidates]))
        def cover_ready(pixmap, position=0):
            if isValid(self) and self.key == key and not pixmap.isNull():
                if self.cover.isNull() or pixmap.width() * pixmap.height() > self.cover.width() * self.cover.height():
                    self.cover = pixmap
                    if self.index < 0:
                        self.current = pixmap
                        self.update()
            if isValid(self) and self.key == key and (pixmap.isNull() or pixmap.width() < 640) and position + 1 < len(candidates):
                self.cache.fetch(candidates[position + 1], lambda image: cover_ready(image, position + 1))
        if candidates and candidates[0]:
            self.cache.fetch(candidates[0], cover_ready)
        # Small YouTube storyboards are navigation thumbnails, not large previews.
        for index, frame in enumerate([item for item in storyboard_frames(task) if item.rect[2] >= 960 and item.rect[3] >= 540] if video else []):
            def frame_ready(pixmap, number=index, spec=frame):
                if isValid(self) and self.key == key and not pixmap.isNull() and pixmap.rect().contains(QRect(*spec.rect)):
                    self.frames[number] = pixmap.copy(QRect(*spec.rect))
                    if self.current.isNull():
                        self.current = self.frames[number]
                        self.index = 0
                        self.update()
                    self.sync_animation()
            self.cache.fetch(frame.url, frame_ready, low_priority=True)
        self.sync_animation()

    def _sharp_frame_ready(self, number, pixmap):
        if not self.video:
            return
        self.frames[number] = pixmap
        if self.current.isNull():
            self.current = pixmap
            self.index = 0
            self.update()
        self.sync_animation()

    def sync_animation(self):
        window = self.window()
        visible = self.video and self.isVisible() and not window.isMinimized()
        if self.extractor:
            self.extractor.set_enabled(visible)
        enabled = visible and len(self.frames) > 1
        if enabled and not self.timer.isActive():
            self.timer.start()
        elif not enabled:
            self.timer.stop()
            self.animation.stop()
            self.fade = 1.0

    def advance(self):
        if not self.isVisible() or self.window().isMinimized() or self.visibleRegion().isEmpty() or not self.frames:
            return
        frames = [self.frames[index] for index in sorted(self.frames)]
        self.index = (self.index + 1) % len(frames)
        self.previous, self.current = self.current, frames[self.index]
        self.animation.stop()
        self.fade = 0.0
        self.animation.start()
        self.update()

    def _fade_changed(self, value):
        self.fade = float(value)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_animation()

    def hideEvent(self, event):
        if self.extractor:
            self.extractor.set_enabled(False)
        self.timer.stop()
        self.animation.stop()
        self.fade = 1.0
        super().hideEvent(event)

    def paintEvent(self, _event):
        colors = palette(self.preferences.theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 10, 10)
        painter.fillPath(clip, QColor(colors["input"]))
        painter.setClipPath(clip)
        if self.current.isNull():
            self.icon.paint(painter, self.width() // 2 - 28, self.height() // 2 - 28, 56, 56)
            return
        def draw(pixmap, opacity):
            if pixmap.isNull():
                return
            painter.setOpacity(opacity)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            if abs(pixmap.width() / pixmap.height() - self.width() / self.height()) > .08:
                key = (pixmap.cacheKey(), self.width(), self.height())
                if key not in self.backdrops:
                    self.backdrops[key] = blurred_backdrop(pixmap, self.size())
                    while len(self.backdrops) > 3:
                        self.backdrops.popitem(last=False)
                backdrop = self.backdrops[key]
                painter.drawPixmap(rect, backdrop, QRectF(backdrop.rect()))
                painter.fillRect(rect, QColor(0, 0, 0, 70))
            size = pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2, size.width(), size.height())
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        if self.fade < 1.0:
            draw(self.previous, 1.0)
        draw(self.current, self.fade)


class SourceLayout(QWidget):
    def __init__(self, information, preview):
        super().__init__()
        self.layout_row = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.layout_row.setContentsMargins(0, 0, 0, 0)
        self.layout_row.setSpacing(20)
        self.layout_row.addWidget(information, 1)
        self.layout_row.addWidget(preview, 1)
        self.preview = preview

    def resizeEvent(self, event):
        vertical = self.width() < 620
        self.layout_row.setDirection(QBoxLayout.Direction.TopToBottom if vertical else QBoxLayout.Direction.LeftToRight)
        self.preview.setMinimumWidth(min(380, self.width()) if vertical else 220)
        self.preview.setMaximumWidth(min(380, self.width()) if vertical else 16777215)
        self.layout_row.setStretch(0, 0 if vertical else 1)
        self.layout_row.setStretch(1, 0 if vertical else 1)
        self.layout_row.setAlignment(self.preview, Qt.AlignmentFlag.AlignHCenter if vertical else Qt.AlignmentFlag(0))
        super().resizeEvent(event)
