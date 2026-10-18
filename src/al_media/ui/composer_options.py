from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from al_media.core.metadata import selection_kind
from al_media.i18n import tr

from .task_options import apply_options, format_time


class ComposerOptions(QFrame):
    changed = Signal()
    accepted = Signal()

    def __init__(self, preferences, parent=None):
        super().__init__(parent)
        self.preferences, self.task, self.loading = preferences, None, False
        self.setObjectName("optionsEditor")
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(16, 16, 16, 16)
        self.column.setSpacing(10)
        self.clip = QCheckBox()
        self.clip.setObjectName("clipToggle")
        self.clip.setFixedHeight(22)
        self.start, self.end = QLineEdit(), QLineEdit()
        self.start.setPlaceholderText("0:00")
        self.start.setFixedHeight(36)
        self.end.setFixedHeight(36)
        times = QWidget()
        row = QHBoxLayout(times)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.start_caption, self.end_caption = QLabel(), QLabel()
        for caption, field in ((self.start_caption, self.start), (self.end_caption, self.end)):
            group = QVBoxLayout()
            group.setSpacing(6)
            caption.setObjectName("fieldCaption")
            group.addWidget(caption)
            group.addWidget(field)
            row.addLayout(group, 1)
        self.column.addWidget(self.clip)
        self.column.addWidget(times)
        self.audio_track, self.subtitles = QComboBox(), QComboBox()
        self.voice_caption, self.subtitles_caption = QLabel(), QLabel()
        for caption in (self.voice_caption, self.subtitles_caption):
            caption.setObjectName("fieldCaption")
        for widget in (self.voice_caption, self.audio_track, self.subtitles_caption, self.subtitles):
            self.column.addWidget(widget)
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.column.addWidget(self.error)
        self.error.hide()
        self.apply_button = QPushButton()
        self.apply_button.setFixedHeight(36)
        self.apply_button.clicked.connect(self.accepted)
        self.column.addWidget(self.apply_button)
        for combo in (self.audio_track, self.subtitles):
            combo.setFixedHeight(36)
            combo.setMinimumWidth(0)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.currentTextChanged.connect(combo.setToolTip)
            combo.currentIndexChanged.connect(self._changed)
        for field in (self.start, self.end):
            field.editingFinished.connect(self._changed)
        self.clip.toggled.connect(self._changed)
        self.set_task(None)

    def set_task(self, task):
        self.task, self.loading = task, True
        lang = self.preferences.language
        self.clip.setText(tr(lang, "save_clip"))
        self.start_caption.setText(tr(lang, "clip_start"))
        self.end_caption.setText(tr(lang, "clip_end"))
        self.apply_button.setText(tr(lang, "apply"))
        self.voice_caption.setText(tr(lang, "audio_track"))
        self.subtitles_caption.setText(tr(lang, "subtitles"))
        self.start.setAccessibleName(tr(lang, "clip_start"))
        self.end.setAccessibleName(tr(lang, "clip_end"))
        self.audio_track.setAccessibleName(tr(lang, "audio_track"))
        self.subtitles.setAccessibleName(tr(lang, "subtitles"))
        self.clip.setChecked(bool(task and (task.clip_start is not None or task.clip_end is not None)))
        self.start.setText(self._time(task.clip_start) if task else "")
        self.end.setText(self._time(task.clip_end) if task else "")
        self.end.setPlaceholderText(self._time(task.duration) if task else "0:00")
        self.audio_track.clear()
        self.audio_track.addItem(tr(lang, "automatic"), "")
        self.subtitles.clear()
        self.subtitles.addItem(tr(lang, "no_subtitles"), None)
        if task:
            if task.audio_tracks:
                for track in task.audio_tracks:
                    self.audio_track.addItem(track["label"] or tr(lang, "source_audio"), track)
                    if task.audio_track_ids and task.audio_track_ids == track["ids"]:
                        self.audio_track.setCurrentIndex(self.audio_track.count() - 1)
            else:
                for language in task.audio_languages:
                    self.audio_track.addItem(language, language)
                self.audio_track.setCurrentIndex(max(0, self.audio_track.findData(task.audio_language)))
            for automatic, supplied in ((False, task.subtitles), (True, task.automatic_captions)):
                for language in sorted(supplied):
                    if language == "live_chat":
                        continue
                    name = language + (" (auto)" if automatic else "")
                    modes = (("SRT", "sidecar"), (tr(lang, "embedded_short"), "embedded")) if selection_kind(task.selection) == "video" else (("SRT", "sidecar"),)
                    for label, mode in modes:
                        self.subtitles.addItem(f"{name} · {label}", (language, automatic, mode))
                        if task.subtitle_language == language and task.subtitle_auto == automatic and task.subtitle_mode == mode:
                            self.subtitles.setCurrentIndex(self.subtitles.count() - 1)
        self.error.clear()
        self.error.hide()
        video = bool(task and selection_kind(task.selection) == "video")
        for widget in (self.voice_caption, self.audio_track, self.subtitles_caption, self.subtitles):
            widget.setVisible(video)
        self.setEnabled(task is not None)
        self.loading = False
        self._sync_fields()

    def _sync_fields(self):
        self.start.setEnabled(self.clip.isChecked())
        self.end.setEnabled(self.clip.isChecked())
        self.audio_track.setEnabled(self.audio_track.count() > 1)
        self.subtitles.setEnabled(self.subtitles.count() > 1)

    @staticmethod
    def _time(value):
        text = format_time(value)
        return text[3:] if text.startswith("00:") else text

    def _changed(self, *_):
        if not self.loading:
            self._sync_fields()
            self.changed.emit()

    def apply(self):
        if not self.task:
            return True
        try:
            video = selection_kind(self.task.selection) == "video"
            choice = self.subtitles.currentData() if video else None
            apply_options(self.task, self.clip.isChecked(), self.start.text(), self.end.text(),
                          self.audio_track.currentData() if video else None, choice[:2] if choice else None, choice[2] if choice else "none")
        except ValueError:
            self.error.setText(tr(self.preferences.language, "clip_invalid"))
            self.error.show()
            return False
        self.error.clear()
        self.error.hide()
        return True


class OptionsPopup(QFrame):
    closed = Signal()

    def __init__(self, anchor, parent):
        super().__init__(parent, Qt.WindowType.Popup)
        self.anchor = anchor
        self.setObjectName("panel")
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(0, 0, 0, 0)

    def show_below(self):
        self.setFixedWidth(max(280, min(360, self.anchor.width())))
        for index in range(self.content.count()):
            widget = self.content.itemAt(index).widget()
            if widget and widget.layout():
                widget.layout().invalidate()
                widget.layout().activate()
        self.content.invalidate()
        self.content.activate()
        self.setFixedHeight(self.content.sizeHint().height())
        origin = self.anchor.mapToGlobal(QPoint(0, self.anchor.height() + 6))
        screen = self.anchor.screen() or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        origin.setX(max(bounds.left(), min(origin.x(), bounds.right() - self.width() + 1)))
        origin.setY(max(bounds.top(), min(origin.y(), bounds.bottom() - self.height() + 1)))
        self.move(origin)
        self.show()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.closed.emit()
