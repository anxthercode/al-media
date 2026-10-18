from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QEasingCurve, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLayout, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from al_media.config import app_root


class BrandMark(QWidget):
    """Render brand vectors at the actual device scale without a bitmap step."""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.source = (app_root() / "assets/sites" / f"{name}.svg").read_text(encoding="utf-8")
        self.renderer = QSvgRenderer(self)
        self.set_color("#a8b7c6")

    def set_color(self, color):
        source = self.source.replace("<svg ", f'<svg fill="{color}" ', 1)
        self.renderer.load(QByteArray(source.encode()))
        self.renderer.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        self.renderer.render(painter, QRectF(self.rect()))


class SegmentedSwitch(QFrame):
    """A single connected control with a moving selection and equal hit areas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("modeSwitch")
        self.setFixedHeight(46)
        self.highlight = QFrame(self)
        self.highlight.setObjectName("modeHighlight")
        self.highlight.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.animation = QPropertyAnimation(self.highlight, b"geometry", self)
        self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(4, 4, 4, 4)
        self.row.setSpacing(4)
        self.buttons = []

    def add_button(self, button):
        button.setObjectName("modeSegment")
        button.setMinimumHeight(36)
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.buttons.append(button)
        self.row.addWidget(button, 1)
        button.toggled.connect(lambda checked: QTimer.singleShot(0, lambda: self.sync(True)) if checked else None)

    def sync(self, animate=False):
        selected = next((button for button in self.buttons if button.isChecked()), None)
        if selected is None:
            return
        target = selected.geometry()
        if self.animation.state() == QPropertyAnimation.State.Running and self.animation.endValue() == target:
            return
        if self.highlight.geometry() == target:
            return
        self.animation.stop()
        if animate and self.isVisible() and self.highlight.geometry().isValid():
            self.animation.setStartValue(self.highlight.geometry())
            self.animation.setEndValue(target)
            self.animation.start()
        else:
            self.highlight.setGeometry(target)
        self.highlight.lower()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.row.activate()
        self.sync(self.animation.state() == QPropertyAnimation.State.Running)

    def showEvent(self, event):
        super().showEvent(event)
        self.row.activate()
        self.sync()


class DisclosureButton(QPushButton):
    """Reserve a separate trailing area for the chevron, including its inset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("disclosure")
        self.setCheckable(True)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self.chevron = QIcon()

    def sizeHint(self):
        size = super().sizeHint()
        return QSize(max(size.width(), self.fontMetrics().horizontalAdvance(self.text()) + 76), 36)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        self.chevron.paint(painter, QRect(self.width() - 30, (self.height() - 16) // 2, 16, 16))


@lru_cache(maxsize=256)
def svg_icon(name: str, color: str = "#a8b7c6", *, site: bool = False) -> QIcon:
    path = app_root() / "assets" / ("sites" if site else "icons") / f"{name}.svg"
    if not path.is_file():
        return QIcon()
    source = path.read_text(encoding="utf-8").replace('stroke="currentColor"', f'stroke="{color}"')
    if site:
        source = source.replace("<svg ", f'<svg fill="{color}" ', 1)
    renderer = QSvgRenderer(QByteArray(source.encode()))
    renderer.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
    icon = QIcon()
    for size in (18, 24, 32, 48, 64):
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        icon.addPixmap(pixmap)
    return icon


class FlowLayout(QLayout):
    """Wrap content-sized controls instead of truncating translated labels."""

    def __init__(self, parent=None, spacing=10):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < self.count() else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < self.count() else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), True)

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        return size

    def sizeHint(self):
        return self.minimumSize()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, False)

    def _arrange(self, rect, measure):
        x, y, row_height = rect.x(), rect.y(), 0
        for item in self.items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            width = min(size.width(), rect.width())
            height = max(size.height(), item.heightForWidth(width)) if item.hasHeightForWidth() else size.height()
            if x > rect.x() and x + width > rect.right() + 1:
                x, y, row_height = rect.x(), y + row_height + self.spacing(), 0
            if not measure:
                item.setGeometry(QRect(x, y, width, height))
            x += width + self.spacing()
            row_height = max(row_height, height)
        return y + row_height - rect.y()


class Foldout(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.toggle = QToolButton()
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setMinimumHeight(36)
        layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.body = QWidget()
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(14)
        self.body.hide()
        layout.addWidget(self.body)
        self.toggle.toggled.connect(self._toggle)

    def _toggle(self, checked):
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.body.setVisible(checked)


def open_local(path: Path) -> bool:
    import os
    import subprocess

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    if os.name == "nt" and path.is_file():
        subprocess.Popen(["explorer.exe", "/select,", str(path.resolve())], creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
