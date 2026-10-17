from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout

from al_media.config import app_root
from al_media.core.metadata import available_selections, selection_kind
from al_media.i18n import format_label, tr
from al_media.models import State, Task

EDITABLE = {State.READY, State.FAILED, State.CANCELLED, State.INTERRUPTED}
BUSY = {State.PENDING_METADATA, State.FETCHING_METADATA, State.QUEUED, State.DOWNLOADING, State.POSTPROCESSING}


class TaskCard(QFrame):
    def __init__(self, task: Task, window):
        super().__init__()
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.task_id, self.window = task.id, window
        self.thumbnail_requested = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)
        self.rail = QFrame()
        self.rail.setFixedWidth(3)
        layout.addWidget(self.rail)
        self.thumbnail = QLabel()
        self.thumbnail.setPixmap(QIcon(str(app_root() / "assets" / "app.ico")).pixmap(32, 32))
        self.thumbnail.setObjectName("thumbnail")
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setFixedSize(128, 72)
        layout.addWidget(self.thumbnail, 0, Qt.AlignmentFlag.AlignTop)
        content = QVBoxLayout()
        content.setSpacing(8)
        heading = QHBoxLayout()
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setObjectName("cardTitle")
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(0)
        heading.addWidget(self.title, 1)
        self.remove = QPushButton("×")
        self.remove.setObjectName("quiet")
        self.remove.setFixedSize(30, 30)
        self.remove.clicked.connect(lambda: window.scheduler.remove(self.task_id))
        heading.addWidget(self.remove, 0, Qt.AlignmentFlag.AlignTop)
        content.addLayout(heading)
        self.details = QLabel()
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setObjectName("muted")
        self.details.setWordWrap(True)
        content.addWidget(self.details)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(5)
        self.bar.setTextVisible(False)
        content.addWidget(self.bar)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        content.addWidget(self.status)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.media_kind = QComboBox()
        self.media_kind.setMaximumWidth(155)
        self.media_kind.currentIndexChanged.connect(self._kind_changed)
        controls.addWidget(self.media_kind)
        self.selection = QComboBox()
        self.selection.setMinimumWidth(175)
        self.selection.setMaximumWidth(250)
        self.selection.currentIndexChanged.connect(self._selection_changed)
        controls.addWidget(self.selection)
        controls.addStretch()
        content.addLayout(controls)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.folder = QPushButton()
        self.folder.setObjectName("quiet")
        self.folder.clicked.connect(self._choose_folder)
        actions.addWidget(self.folder)
        actions.addStretch()
        self.start = QPushButton()
        self.start.setObjectName("primary")
        self.start.clicked.connect(lambda: window.start_task(self.task_id))
        self.cancel = QPushButton()
        self.cancel.clicked.connect(lambda: window.scheduler.cancel(self.task_id))
        self.open_file = QPushButton()
        self.open_file.setObjectName("primary")
        self.open_file.clicked.connect(lambda: window.open_result(self.task_id, False))
        self.open_folder = QPushButton()
        self.open_folder.clicked.connect(lambda: window.open_result(self.task_id, True))
        for button in (self.start, self.cancel, self.open_file, self.open_folder):
            actions.addWidget(button)
        content.addLayout(actions)
        layout.addLayout(content, 1)
        self.render(task)

    def _kind_changed(self):
        task = self.window.scheduler.tasks.get(self.task_id)
        if task and task.state in EDITABLE and self.media_kind.currentData():
            task.selection = {"video": "best", "mp3": "mp3:192", "audio": "audio"}[self.media_kind.currentData()]
            self.window.scheduler.database.save(task)
            self.render(task)

    def _selection_changed(self):
        task = self.window.scheduler.tasks.get(self.task_id)
        if task and task.state in EDITABLE and self.selection.currentData():
            task.selection = self.selection.currentData()
            self.window.scheduler.database.save(task)

    def _choose_folder(self):
        task = self.window.scheduler.tasks[self.task_id]
        folder = QFileDialog.getExistingDirectory(self, tr(self.window.preferences.language, "path"), task.folder)
        if folder and task.state in EDITABLE:
            task.folder = folder
            self.window.scheduler.database.save(task)
            self.render(task)

    def render(self, task):
        language = self.window.preferences.language
        editable = task.state in EDITABLE
        self.title.setText(task.title or tr(language, "download_failed" if task.state == State.FAILED else
                                           "fetching_metadata" if task.state in BUSY else task.state.value))
        self.title.setToolTip(task.url)
        duration = f"{int(task.duration // 60)}:{int(task.duration % 60):02}" if task.duration else ""
        self.details.setText("  ·  ".join(filter(None, [task.source or urlsplit(task.url).netloc, task.author, duration])))
        self.details.setToolTip(task.url)
        self.folder.setText(tr(language, "destination"))
        self.folder.setToolTip(task.folder)
        options = available_selections({"formats": task.formats})
        if task.playlist:
            options = [("best", ""), ("audio", ""), ("mp3:192", "")]
        kind = selection_kind(task.selection)
        kinds = {selection_kind(key) for key, _ in options}
        self.media_kind.blockSignals(True)
        self.media_kind.clear()
        for value in ("video", "mp3", "audio"):
            if value in kinds:
                self.media_kind.addItem(tr(language, value + "_mode"), value)
        self.media_kind.setCurrentIndex(max(0, self.media_kind.findData(kind)))
        self.media_kind.blockSignals(False)
        self.media_kind.setVisible(editable and bool(options))
        self.media_kind.setToolTip(tr(language, "download_type"))
        self.media_kind.setAccessibleName(tr(language, "download_type"))
        heights = [int(key.split(":")[1]) for key, _ in options if key.startswith("video:")]
        max_height = max(heights, default=None)
        options = [(key, label) for key, label in options if selection_kind(key) == kind
                   and (key != "mp4" or task.selection == "mp4") and key != f"video:{max_height}"]
        self.selection.blockSignals(True)
        self.selection.clear()
        for value, _ in options:
            self.selection.addItem(format_label(language, value, max_height), value)
        self.selection.setCurrentIndex(max(0, self.selection.findData(task.selection)))
        self.selection.blockSignals(False)
        self.selection.setVisible(editable and bool(options))
        self.selection.setToolTip(tr(language, "video_quality" if kind == "video" else "audio_quality"))
        self.selection.setAccessibleName(tr(language, "video_quality" if kind == "video" else "audio_quality"))
        self.folder.setVisible(editable and bool(options))
        parts = [tr(language, task.state.value)]
        if task.state in BUSY and task.error:
            parts.append(tr(language, task.error))
        if task.state == State.FAILED:
            parts.append(tr(language, task.error))
        elif task.state == State.DOWNLOADING:
            if task.percent is not None:
                parts.append(f"{task.percent:.0f}%")
            if task.downloaded is not None:
                size = f"{task.downloaded / 1048576:.1f} MB"
                if task.total:
                    size += f" / {task.total / 1048576:.1f} MB"
                parts.append(size)
            if task.speed:
                parts.append(f"{task.speed / 1048576:.1f} MB/s")
            if task.eta is not None:
                parts.append(f"{tr(language, 'remaining')} {int(task.eta)//60}:{int(task.eta)%60:02}")
        elif task.state == State.COMPLETED:
            parts.append(format_label(language, task.selection))
        self.status.setText("  ·  ".join(parts))
        self.bar.setVisible(task.state in BUSY or task.state == State.COMPLETED)
        if task.percent is None and task.state in {State.FETCHING_METADATA, State.DOWNLOADING, State.POSTPROCESSING}:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(round(task.percent or 0))
        color = "#e77c82" if task.state == State.FAILED else "#62cda1" if task.state == State.COMPLETED else "#5cdbca" if task.state in BUSY else "#7795b9"
        self.rail.setStyleSheet(f"background: {color}; border-radius: 1px;")
        self.start.setText(tr(language, "start" if task.state == State.READY else "retry"))
        self.start.setVisible(editable)
        self.start.setEnabled(not self.window.installing)
        self.cancel.setText(tr(language, "cancel"))
        self.cancel.setVisible(task.state in BUSY)
        self.remove.setToolTip(tr(language, "remove"))
        self.remove.setAccessibleName(tr(language, "remove"))
        self.remove.setEnabled(task.state not in BUSY)
        self.open_file.setText(tr(language, "open"))
        self.open_folder.setText(tr(language, "folder"))
        for button in (self.open_file, self.open_folder):
            button.setVisible(task.state == State.COMPLETED)
            button.setEnabled(Path(task.final_path).is_file())
