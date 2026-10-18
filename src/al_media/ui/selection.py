from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QButtonGroup, QComboBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from al_media.core.metadata import preferred_selection, selection_kind, task_selections, video_heights
from al_media.i18n import format_label, tr

from .themes import palette
from .widgets import SegmentedSwitch, svg_icon


def default_selection(task, prefs):
    return preferred_selection(task, prefs)


class FormatPicker(QWidget):
    changed = Signal(str)

    def __init__(self, prefs, parent=None):
        super().__init__(parent)
        self.prefs = prefs
        self.task = None
        self.selection = prefs.video_quality if prefs.media_mode == "video" else f"mp3:{prefs.mp3_bitrate}" if prefs.audio_format == "mp3" else prefs.audio_format
        self.updating = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.modes = SegmentedSwitch()
        self.group = QButtonGroup(self)
        self.video, self.audio = QPushButton(), QPushButton()
        for index, button in enumerate((self.video, self.audio)):
            button.setCheckable(True)
            button.setIconSize(QSize(18, 18))
            self.group.addButton(button, index)
            self.modes.add_button(button)
        self.group.idClicked.connect(self._mode_changed)
        self.quality_field, self.quality_caption, self.quality = self._field(layout)
        self.format_field, self.format_caption, self.audio_format = self._field(layout)
        self.bitrate_field, self.bitrate_caption, self.bitrate = self._field(layout)
        self.quality.currentIndexChanged.connect(self._quality_changed)
        self.audio_format.currentIndexChanged.connect(self._format_changed)
        self.bitrate.currentIndexChanged.connect(self._bitrate_changed)
        self.render()

    @staticmethod
    def _field(layout):
        widget = QWidget()
        row = QVBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        caption = QLabel()
        caption.setObjectName("fieldCaption")
        combo = QComboBox()
        combo.setMinimumContentsLength(8)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setFixedHeight(36)
        combo.currentTextChanged.connect(combo.setToolTip)
        row.addWidget(caption)
        row.addWidget(combo)
        layout.addWidget(widget, 1)
        return widget, caption, combo

    @staticmethod
    def _fill(combo, choices, selected):
        combo.blockSignals(True)
        combo.clear()
        for key, label in choices:
            combo.addItem(label, key)
        combo.setCurrentIndex(max(0, combo.findData(selected)))
        combo.blockSignals(False)

    def set_task(self, task):
        self.task = task
        if task:
            self.selection = task.selection
        self.render()

    def render(self):
        self.updating = True
        lang = self.prefs.language
        keys = [key for key, _ in task_selections(self.task)] if self.task else []
        is_video = selection_kind(self.selection) == "video"
        self.video.setText(tr(lang, "video_mode"))
        self.audio.setText(tr(lang, "audio_mode"))
        self.video.setChecked(is_video)
        self.audio.setChecked(not is_video)
        colors = palette(self.prefs.theme)
        self.video.setIcon(svg_icon("video", colors["download"] if is_video else colors["muted"]))
        self.audio.setIcon(svg_icon("audio", colors["download"] if not is_video else colors["muted"]))
        self.video.setEnabled(not keys or any(selection_kind(key) == "video" for key in keys))
        self.audio.setEnabled(not keys or any(selection_kind(key) != "video" for key in keys))
        maximum = max(video_heights(self.task), default=None) if self.task else None
        video_keys = [key for key in keys if selection_kind(key) == "video" and key != "mp4" and key != f"video:{maximum}"]
        self._fill(self.quality, [(key, format_label(lang, key, maximum)) for key in video_keys], self.selection)
        formats = []
        if "audio" in keys:
            formats.append(("audio", tr(lang, "source_format")))
        if any(key.startswith("mp3:") for key in keys):
            formats.append(("mp3", "MP3"))
        if "m4a" in keys:
            formats.append(("m4a", "M4A"))
        self._fill(self.audio_format, formats, "mp3" if self.selection.startswith("mp3:") else self.selection)
        self._fill(self.bitrate, [(f"mp3:{rate}", f"{rate} {tr(lang, 'kbps')}") for rate in (320, 192, 128)], self.selection)
        self.quality_caption.setText(tr(lang, "video_quality"))
        self.format_caption.setText(tr(lang, "audio_quality"))
        self.bitrate_caption.setText(tr(lang, "bitrate"))
        self.quality.setAccessibleName(tr(lang, "video_quality"))
        self.audio_format.setAccessibleName(tr(lang, "audio_quality"))
        self.bitrate.setAccessibleName(tr(lang, "bitrate"))
        self.quality_field.setVisible(bool(video_keys) and is_video)
        self.format_field.setVisible(bool(formats) and not is_video)
        self.bitrate_field.setVisible(bool(formats) and self.selection.startswith("mp3:"))
        self.modes.update()
        self.updating = False

    def _choose(self, selection):
        if self.updating or not selection:
            return
        self.selection = selection
        if self.task:
            self.task.selection = selection
        self.render()
        self.changed.emit(selection)

    def _mode_changed(self, index):
        wanted = self.prefs.video_quality if index == 0 else f"mp3:{self.prefs.mp3_bitrate}" if self.prefs.audio_format == "mp3" else self.prefs.audio_format
        if self.task:
            keys = [key for key, _ in task_selections(self.task)]
            kind = "video" if index == 0 else "audio"
            matching = [key for key in keys if (selection_kind(key) == "video") == (kind == "video")]
            wanted = wanted if wanted in matching else matching[0] if matching else wanted
        self._choose(wanted)

    def _quality_changed(self):
        self._choose(self.quality.currentData())

    def _format_changed(self):
        value = self.audio_format.currentData()
        self._choose(f"mp3:{self.prefs.mp3_bitrate}" if value == "mp3" else value)

    def _bitrate_changed(self):
        self._choose(self.bitrate.currentData())
