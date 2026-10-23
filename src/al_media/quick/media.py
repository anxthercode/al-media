from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import Property, QObject, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

from al_media.application.images import ImageCache, storyboard_frames
from al_media.config import app_root
from al_media.core.metadata import selection_kind
from al_media.core.preview_frames import FrameExtractor


class IconProvider(QQuickImageProvider):
    def __init__(self, icons_root):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.icons_root = icons_root

    def requestImage(self, ident, size, requestedSize):

        name, _, color = ident.partition("/")
        name = name if name.replace("-", "").isalnum() else "download"
        path = self.icons_root / (name + ".svg")
        if not path.is_file():
            path = app_root() / "assets" / "icons" / (name + ".svg")
        if not path.is_file():
            path = app_root() / "assets" / "sites" / (name + ".svg")
        data = path.read_bytes() if path.is_file() else b""
        if color and len(color) in {6, 8} and all(c in "0123456789abcdefABCDEF" for c in color):
            import re

            data = data.replace(b"currentColor", b"#" + color.encode())
            data = re.sub(rb'(stroke|fill)="#[0-9a-fA-F]{3,8}"', lambda m: m[1] + b'="#' + color.encode() + b'"', data)
            # Brand files use SVG's implicit black fill. Set the inherited fill
            # on the root, while preserving explicit fill="none" on line icons.
            root_tag = re.search(rb"<svg\b[^>]*>", data)
            if root_tag and not re.search(rb"\bfill\s*=", root_tag[0]):
                # License comments can precede <svg>; inspect the actual root
                # instead of injecting a duplicate fill into outlined icons.
                tinted_root = root_tag[0].replace(b"<svg ", b'<svg fill="#' + color.encode() + b'" ', 1)
                data = data[:root_tag.start()] + tinted_root + data[root_tag.end():]
        renderer = QSvgRenderer(data)
        dimensions = requestedSize if requestedSize.width() > 0 and requestedSize.height() > 0 else QSize(24, 24)
        dimensions = dimensions.boundedTo(QSize(256, 256))
        result = QImage(dimensions, QImage.Format.Format_ARGB32_Premultiplied)
        result.fill(Qt.GlobalColor.transparent)
        if renderer.isValid():
            painter = QPainter(result)
            renderer.render(painter)
            painter.end()
        size.setWidth(dimensions.width())
        size.setHeight(dimensions.height())
        return result


class PreviewProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.images: OrderedDict[str, QImage] = OrderedDict()
        self.serial = 0

    def put(self, image):
        self.serial += 1
        key = str(self.serial)
        self.images[key] = image.toImage() if hasattr(image, "toImage") else image
        while len(self.images) > 16:
            self.images.popitem(last=False)
        return "image://preview/" + key

    def requestImage(self, ident, size, requestedSize):
        image = self.images.get(ident, QImage())
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


class MediaViewModel(QObject):
    changed = Signal()

    def __init__(self, tools, provider, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.cache = ImageCache(self)
        self.extractor = FrameExtractor(tools.get("ffmpeg", ""), self)
        self.extractor.ready.connect(self._frame)
        self._source = ""
        self.task = None
        self.signature = None
        self.generation = 0
        self.frames = {}
        self.index = 0
        self.active = True
        self.timer = QTimer(self, interval=2400)
        self.timer.timeout.connect(self._advance)

    @Property(str, notify=changed)
    def source(self):
        return self._source

    def set_task(self, task):
        signature = (task.url, task.clip_start, task.clip_end, task.duration, task.final_path, selection_kind(task.selection)) if task else None
        if task is self.task and signature == self.signature:
            return
        self.signature = signature
        old_url = self.task.url if self.task else None
        self.generation += 1
        generation = self.generation
        self.task = task
        self.frames.clear()
        if not task or task.url != old_url:
            self._source = ""
        self.timer.stop()
        self.extractor.set_task(task)
        if task:
            candidates = task.thumbnail_candidates or ([task.thumbnail] if task.thumbnail else [])
            self._poster(candidates, generation)
            if selection_kind(task.selection) == "video":
                for index, frame in enumerate(storyboard_frames(task)):

                    def ready(image, index=index, frame=frame, generation=generation):
                        if generation == self.generation and not image.isNull():
                            self._frame(index, image.copy(*frame.rect))

                    self.cache.fetch(frame.url, ready, low_priority=True)
                self.extractor.set_enabled(self.active)
            else:
                self.extractor.set_enabled(False)
        self.changed.emit()

    def _poster(self, candidates, generation):
        if not candidates:
            return

        def ready(image):
            if generation != self.generation:
                return
            if not image.isNull():
                self._source = self.provider.put(image)
                self.changed.emit()
            else:
                self._poster(candidates[1:], generation)

        self.cache.fetch(candidates[0], ready)

    def _frame(self, index, image):
        self.frames[index] = image
        if self.active and not self.timer.isActive():
            self.timer.start()

    def _advance(self):
        if self.frames and self.active:
            keys = sorted(self.frames)
            self.index = (self.index + 1) % len(keys)
            self._source = self.provider.put(self.frames[keys[self.index]])
            self.changed.emit()

    @Slot(bool)
    def setActive(self, active):
        self.active = active
        self.extractor.set_enabled(active and bool(self.task) and selection_kind(self.task.selection) == "video")
        if active and self.frames:
            self.timer.start()
        else:
            self.timer.stop()

    def shutdown(self):
        self.active = False
        self.generation += 1
        self.timer.stop()
        self.extractor.shutdown()
        self.cache.shutdown()
