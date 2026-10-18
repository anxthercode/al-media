from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QApplication, QBoxLayout, QFrame, QHBoxLayout, QLabel, QMenu, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from al_media.core.metadata import estimate_size, selection_kind, video_heights
from al_media.i18n import tr
from al_media.models import State

from .themes import palette
from .widgets import svg_icon

EDITABLE = {State.READY, State.FAILED, State.CANCELLED, State.INTERRUPTED}
BUSY = {State.PENDING_METADATA, State.FETCHING_METADATA, State.QUEUED, State.DOWNLOADING, State.POSTPROCESSING}


def size_label(value, language):
    divisor, unit = (1073741824, "gb") if value >= 1073741824 else (1048576, "mb")
    amount = f"{value / divisor:.1f}"
    if language != "en":
        amount = amount.replace(".", ",")
    return f"{amount} {tr(language, unit)}"


def output_details(task, language):
    if task.selection.startswith("mp3:"):
        rate = round(task.output_bitrate / 1000) if task.output_bitrate else int(task.selection.split(":")[1])
        return ["MP3", f"{rate} {tr(language, 'kbps')}"]
    if selection_kind(task.selection) != "video":
        return [Path(task.final_path).suffix.lstrip(".").upper() if task.final_path else "M4A" if task.selection == "m4a" else tr(language, "source_format")]
    height = int(task.selection.split(":")[1]) if task.selection.startswith("video:") else max(video_heights(task), default=None)
    container = Path(task.final_path).suffix.lstrip(".").upper() if task.final_path else (
        "MKV" if task.subtitle_mode == "embedded" else "MP4" if task.selection == "mp4" else tr(language, "video_mode"))
    return [container, f"{height}p" if height else ""]


class ElidedLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        painter.setFont(self.font())
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)


class TaskCard(QFrame):
    def __init__(self, task, window):
        super().__init__()
        self.task_id, self.window = task.id, window
        self.thumbnail_requested = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.outer = QVBoxLayout(self)
        self.outer.setSpacing(10)
        self.row = QHBoxLayout()
        self.row.setSpacing(12)
        self.thumbnail = QLabel()
        self.thumbnail.setObjectName("thumbnail")
        self.thumbnail.setFixedSize(64, 44)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setPixmap(window.windowIcon().pixmap(QSize(24, 24), self.devicePixelRatioF()))
        self.row.addWidget(self.thumbnail)
        self.copy_and_actions = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.copy_and_actions.setSpacing(16)
        content = QVBoxLayout()
        content.setSpacing(5)
        self.title = ElidedLabel()
        self.title.setObjectName("cardTitle")
        self.details = ElidedLabel()
        self.details.setObjectName("rowDetails")
        content.addWidget(self.title)
        content.addWidget(self.details)
        self.copy_and_actions.addLayout(content, 1)
        self.actions_box = QWidget()
        actions = QHBoxLayout(self.actions_box)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        stats = QVBoxLayout()
        stats.setSpacing(4)
        self.status, self.transfer = QLabel(), QLabel()
        for label in (self.status, self.transfer):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setObjectName("rowDetails")
            label.setAlignment(Qt.AlignmentFlag.AlignRight)
        stats.addWidget(self.status)
        stats.addWidget(self.transfer)
        actions.addLayout(stats)
        self.actions = {}
        for key in ("start", "cancel", "open", "folder"):
            button = QPushButton()
            button.setIconSize(QSize(18, 18))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if key == "cancel":
                button.setObjectName("rowAction")
                button.setFixedSize(32, 32)
            else:
                button.setMinimumHeight(36)
            actions.addWidget(button)
            self.actions[key] = button
        self.start, self.cancel = self.actions["start"], self.actions["cancel"]
        self.open_file, self.open_folder = self.actions["open"], self.actions["folder"]
        self.start.clicked.connect(lambda: window.start_task(self.task_id))
        self.cancel.clicked.connect(lambda: window.scheduler.cancel(self.task_id))
        self.open_file.clicked.connect(lambda: window.open_result(self.task_id, False))
        self.open_folder.clicked.connect(lambda: window.open_result(self.task_id, True))
        self.menu_button = QPushButton()
        self.menu_button.setObjectName("rowAction")
        self.menu_button.setFixedSize(32, 32)
        self.menu_button.setIconSize(QSize(18, 18))
        self.menu_button.clicked.connect(self._menu)
        self.remove = self.menu_button
        actions.addWidget(self.menu_button)
        self.copy_and_actions.addWidget(self.actions_box)
        self.row.addLayout(self.copy_and_actions, 1)
        self.outer.addLayout(self.row)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(5)
        self.bar.setTextVisible(False)
        self.outer.addWidget(self.bar)
        for label in (self.thumbnail, self.title, self.details):
            label.installEventFilter(self)
        self.render(task)

    def resizeEvent(self, event):
        task = self.window.scheduler.tasks.get(self.task_id)
        self.copy_and_actions.setDirection(QBoxLayout.Direction.TopToBottom if task and task.state == State.COMPLETED and self.width() < 850 else QBoxLayout.Direction.LeftToRight)
        super().resizeEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            self.window.open_result(self.task_id, False)
            return True
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.window.select_task(self.task_id)
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window.select_task(self.task_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window.open_result(self.task_id, False)
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.window.open_result(self.task_id, False)
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        self._menu(event.globalPos())

    def _menu(self, position=None):
        task = self.window.scheduler.tasks[self.task_id]
        lang = self.window.preferences.language
        menu = QMenu(self)
        if task.state in EDITABLE:
            menu.addAction(tr(lang, "advanced"), lambda: self.window.edit_options(task))
        menu.addAction(tr(lang, "copy_link"), lambda: QApplication.clipboard().setText(task.url))
        remove = menu.addAction(tr(lang, "remove"), lambda: self.window.scheduler.remove(self.task_id))
        remove.setEnabled(task.state not in BUSY)
        menu.exec(position if position is not None and not isinstance(position, bool) else self.mapToGlobal(self.rect().bottomRight()))
        menu.deleteLater()

    def render(self, task):
        lang, colors = self.window.preferences.language, palette(self.window.preferences.theme)
        complete = task.state == State.COMPLETED
        changed = self.objectName() != ("card" if complete else "transferRow")
        if changed:
            self.setObjectName("card" if complete else "transferRow")
            self.outer.setContentsMargins(14, 12, 14, 12) if complete else self.outer.setContentsMargins(0, 12, 0, 8)
        self.thumbnail.setVisible(complete)
        name = Path(task.final_path).name if complete and task.final_path else task.title or task.url
        self.title.setText(name)
        self.title.setToolTip(name)
        parts = ([] if complete else [task.source or urlsplit(task.url).hostname or ""]) + output_details(task, lang)
        amount = task.total or estimate_size(task)
        if complete and task.final_path:
            try:
                amount = Path(task.final_path).stat().st_size
            except OSError:
                pass
        if amount:
            parts.append(size_label(amount, lang))
        self.details.setText(" · ".join(part for part in parts if part))
        self.details.setToolTip(self.details.text())
        stage = task.processing_stage if task.state == State.POSTPROCESSING and task.processing_stage else task.state.value
        status = f"{task.percent:.0f}%" if task.state == State.DOWNLOADING and task.percent is not None else tr(lang, stage)
        if task.error:
            status += " · " + tr(lang, task.error)
        self.status.setText("" if complete else status)
        self.status.setStyleSheet(f"color: {colors['download'] if task.state == State.DOWNLOADING else colors['muted']};")
        self.status.setVisible(not complete)
        self.status.setToolTip(status)
        if task.error:
            self.status.setWordWrap(True)
            self.status.setMaximumWidth(320)
        else:
            self.status.setWordWrap(False)
            self.status.setMaximumWidth(16777215)
        details = []
        if task.state == State.DOWNLOADING:
            if task.speed and task.speed > 0:
                details.append(f"{task.speed / 1048576:.1f} {tr(lang, 'mb_per_second')}")
            if task.eta is not None and task.eta >= 0:
                details.append(f"{tr(lang, 'remaining')} {int(task.eta)//60}:{int(task.eta)%60:02}")
        self.transfer.setText(" · ".join(details))
        self.transfer.setVisible(bool(details))
        self.bar.setVisible(task.state in {State.DOWNLOADING, State.POSTPROCESSING, State.FETCHING_METADATA})
        if task.state != State.DOWNLOADING or task.percent is None:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(max(0, min(100, round(task.percent))))
        self.start.setVisible(task.state in EDITABLE)
        self.start.setText(tr(lang, "retry" if task.state == State.FAILED else "resume" if task.state in {State.CANCELLED, State.INTERRUPTED} else "start"))
        self.start.setIcon(svg_icon("play", colors["muted"]))
        self.cancel.setVisible(task.state in BUSY)
        for key, icon in (("cancel", "close"), ("open", "play"), ("folder", "folderOpen")):
            button = self.actions[key]
            button.setIcon(svg_icon(icon, colors["muted"]))
            button.setToolTip(tr(lang, key))
            button.setAccessibleName(tr(lang, key))
            if key != "cancel":
                button.setVisible(complete)
                button.setText(tr(lang, key))
                button.setEnabled(bool(task.final_path) and Path(task.final_path).is_file())
        self.menu_button.setVisible(not complete and task.state not in BUSY)
        self.menu_button.setIcon(svg_icon("ellipsis", colors["muted"]))
        self.menu_button.setToolTip(tr(lang, "task_actions"))
        self.menu_button.setAccessibleName(tr(lang, "task_actions"))
        if changed:
            self.style().unpolish(self)
            self.style().polish(self)
