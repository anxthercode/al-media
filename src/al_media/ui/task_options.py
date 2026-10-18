from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from al_media.core.metadata import selection_kind, task_selections
from al_media.i18n import tr

from .widgets import FlowLayout


def parse_time(value: str) -> float | None:
    if not value.strip():
        return None
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) > 3:
        raise ValueError("time")
    numbers = [float(part) for part in parts]
    if any(not math.isfinite(part) or part < 0 for part in numbers):
        raise ValueError("time")
    if len(numbers) > 1 and any(part >= 60 for part in numbers[1:]):
        raise ValueError("time")
    result = 0.0
    for part in numbers:
        result = result * 60 + part
    return result


def format_time(value):
    if value is None:
        return ""
    seconds = int(value)
    return f"{seconds//3600:02}:{seconds//60%60:02}:{value%60:06.3f}".rstrip("0").rstrip(".")


def apply_options(task, clip, start_text, end_text, track, subtitles, subtitle_mode):
    start = end = None
    if clip:
        start = parse_time(start_text) or 0.0
        end = parse_time(end_text)
        if (end is not None and end <= start or task.duration is not None and
                (start >= task.duration or end is not None and end > task.duration)):
            raise ValueError("range")
        if end is None:
            end = task.duration
        if start == 0 and end is None:
            raise ValueError("range")
    before = (task.clip_start, task.clip_end, task.audio_language, tuple(task.audio_track_ids), task.subtitle_language, task.subtitle_auto, task.subtitle_mode)
    task.clip_start, task.clip_end = start, end
    task.audio_language = track.get("language", "") if isinstance(track, dict) else track or ""
    task.audio_track_ids = list(track["ids"]) if isinstance(track, dict) else []
    task.subtitle_language = subtitles[0] if subtitles else ""
    task.subtitle_auto = bool(subtitles and subtitles[1])
    task.subtitle_mode = subtitle_mode if subtitles else "none"
    if task.selection == "m4a" and "m4a" not in {key for key, _ in task_selections(task)}:
        task.selection = "audio"
    after = (task.clip_start, task.clip_end, task.audio_language, tuple(task.audio_track_ids), task.subtitle_language, task.subtitle_auto, task.subtitle_mode)
    if before != after:
        task.output_stem = ""
        task.naming_version = 2


class TaskOptionsDialog(QDialog):
    def __init__(self, task, preferences, parent=None):
        super().__init__(parent)
        self.task = task
        self.language = preferences.language
        self.setWindowTitle(tr(self.language, "advanced"))
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        self.clip = QCheckBox(tr(self.language, "clip"))
        self.clip.setChecked(task.clip_start is not None or task.clip_end is not None)
        layout.addWidget(self.clip)
        time_row = QHBoxLayout()
        self.start, self.end = QLineEdit(format_time(task.clip_start)), QLineEdit(format_time(task.clip_end))
        self.start.setPlaceholderText("00:00")
        self.end.setPlaceholderText(format_time(task.duration) or "00:00")
        for key, field in (("clip_start", self.start), ("clip_end", self.end)):
            field.setAccessibleName(tr(self.language, key))
            time_row.addWidget(QLabel(tr(self.language, key)))
            time_row.addWidget(field, 1)
        layout.addLayout(time_row)
        self.clip.toggled.connect(self._clip_changed)
        self._clip_changed(self.clip.isChecked())
        self.audio_track = QComboBox()
        self.audio_track.addItem(tr(self.language, "automatic"), "")
        if task.audio_tracks:
            for track in task.audio_tracks:
                self.audio_track.addItem(track["label"] or tr(self.language, "source_audio"), track)
                if task.audio_track_ids and task.audio_track_ids == track["ids"]:
                    self.audio_track.setCurrentIndex(self.audio_track.count() - 1)
        else:
            for language in task.audio_languages:
                self.audio_track.addItem(language, language)
            self.audio_track.setCurrentIndex(max(0, self.audio_track.findData(task.audio_language)))
        if task.audio_languages or len(task.audio_tracks) > 1:
            layout.addWidget(QLabel(tr(self.language, "audio_track")))
            layout.addWidget(self.audio_track)
        self.subtitles = QComboBox()
        self.subtitles.addItem(tr(self.language, "none"), None)
        for automatic, supplied in ((False, task.subtitles), (True, task.automatic_captions)):
            for language in sorted(supplied):
                if language == "live_chat":
                    continue
                label = language + (f" · {tr(self.language, 'auto_captions')}" if automatic else "")
                data = (language, automatic)
                self.subtitles.addItem(label, data)
                if task.subtitle_language == language and task.subtitle_auto == automatic:
                    self.subtitles.setCurrentIndex(self.subtitles.count() - 1)
        self.subtitle_mode = QComboBox()
        self.subtitle_mode.addItem(tr(self.language, "sidecar"), "sidecar")
        if selection_kind(task.selection) == "video":
            self.subtitle_mode.addItem(tr(self.language, "embedded"), "embedded")
        self.subtitle_mode.setCurrentIndex(max(0, self.subtitle_mode.findData(task.subtitle_mode)))
        if self.subtitles.count() > 1:
            layout.addWidget(QLabel(tr(self.language, "subtitles")))
            layout.addWidget(self.subtitles)
            layout.addWidget(self.subtitle_mode)
        self.subtitles.currentIndexChanged.connect(lambda: self.subtitle_mode.setEnabled(self.subtitles.currentData() is not None))
        self.subtitle_mode.setEnabled(self.subtitles.currentData() is not None)
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel, apply = QPushButton(tr(self.language, "cancel")), QPushButton(tr(self.language, "apply"))
        apply.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        apply.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(apply)
        layout.addLayout(buttons)

    def _clip_changed(self, checked):
        self.start.setEnabled(checked)
        self.end.setEnabled(checked)

    def accept(self):
        try:
            apply_options(self.task, self.clip.isChecked(), self.start.text(), self.end.text(),
                          self.audio_track.currentData(), self.subtitles.currentData(), self.subtitle_mode.currentData())
        except ValueError:
            self.error.setText(tr(self.language, "clip_invalid"))
            return
        super().accept()


class PlaylistDialog(QDialog):
    def __init__(self, task, language, parent=None):
        super().__init__(parent)
        self.task, self.language = task, language
        self.setWindowTitle(tr(language, "playlist"))
        self.resize(640, 540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel(task.title)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel(tr(language, "playlist_items")))
        buttons = FlowLayout()
        for key, checked in (("select_all", True), ("select_none", False)):
            button = QPushButton(tr(language, key))
            button.clicked.connect(lambda _checked=False, value=checked: self._select(value))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.list = QListWidget()
        for entry in task.playlist_entries:
            item = QListWidgetItem(f"{entry['index']:02} · {entry['title']}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            if entry["url"]:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setToolTip(tr(language, "unavailable"))
            self.list.addItem(item)
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.count = QLabel()
        row.addWidget(self.count, 1)
        cancel = QPushButton(tr(language, "cancel"))
        self.add = QPushButton(tr(language, "add_links"))
        self.add.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        self.add.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self.add)
        layout.addLayout(row)
        self.list.itemChanged.connect(self._update_count)
        self._update_count()

    def _select(self, checked):
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(Qt.ItemDataRole.UserRole)["url"]:
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def _update_count(self, *_):
        count = len(self.selected_entries())
        self.count.setText(f"{count} / {self.list.count()}")
        self.add.setEnabled(count > 0)

    def selected_entries(self):
        return [self.list.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.list.count())
                if self.list.item(index).checkState() == Qt.CheckState.Checked]
