from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyledItemDelegate,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from al_media import APP_NAME, __version__
from al_media.config import Preferences, app_root
from al_media.core.engine import EngineJob
from al_media.core.metadata import available_selections, estimate_size, parse_urls, populate_task
from al_media.core.scheduler import Scheduler
from al_media.core.source_probe import SourceProbe
from al_media.i18n import tr
from al_media.models import State, Task

from .composer import downloads_page
from .media_preview import ImageCache
from .pages import about_page, settings_page
from .selection import default_selection
from .task_card import BUSY, TaskCard
from .themes import palette, stylesheet
from .widgets import open_local, svg_icon


class MainWindow(QMainWindow):
    def __init__(self, scheduler: Scheduler, preferences: Preferences, probe_tools: bool = True):
        super().__init__()
        self.scheduler, self.preferences = scheduler, preferences
        self.cards = {}
        self.texts, self.icon_buttons, self.preview_jobs = [], [], []
        self.images = ImageCache(self)
        self.source_probe = SourceProbe(scheduler.tools.get("ffprobe"), self)
        self.source_probe.updated.connect(self._source_probe_ready)
        self.preview_task = None
        self.selected_task_id = ""
        self.explicit_exit = False
        self.preview_job = None
        self.preview_url = ""
        self.installing = False
        self.closing = False
        self.settings_loading = True
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(app_root() / "assets/app.ico")))
        self.setMinimumSize(960, 640)
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        self.resize(min(1200, max(960, area.width() - 24)) if area else 1200,
                    min(840, max(640, area.height() - 48)) if area else 840)
        self.setAcceptDrops(True)
        shell = QWidget()
        shell.setObjectName("shell")
        self.setCentralWidget(shell)
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(184)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 12)
        side.setSpacing(8)
        brand_header = QFrame()
        brand_header.setObjectName("brandHeader")
        brand_header.setFixedHeight(64)
        brand_row = QHBoxLayout(brand_header)
        brand_row.setContentsMargins(20, 0, 16, 0)
        brand_row.setSpacing(10)
        brand_icon = QLabel()
        brand_icon.setPixmap(self.windowIcon().pixmap(QSize(28, 28), self.devicePixelRatioF()))
        brand_row.addWidget(brand_icon)
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        brand_row.addWidget(brand, 1)
        side.addWidget(brand_header)
        side.addSpacing(12)
        self.nav = QButtonGroup(self)
        self.nav_buttons = []
        for index, (key, icon) in enumerate((("downloads", "download"), ("settings", "settings"), ("about", "info"))):
            if index == 2:
                side.addStretch()
            button = self._button(key, lambda _checked=False, page=index: self._navigate(page), icon=icon)
            button.setObjectName("nav")
            button.setCheckable(True)
            self.nav.addButton(button, index)
            self.nav_buttons.append(button)
            wrap = QWidget()
            row = QHBoxLayout(wrap)
            row.setContentsMargins(12, 0, 12, 0)
            row.addWidget(button)
            side.addWidget(wrap)
        root.addWidget(sidebar)
        workspace = QWidget()
        outer = QVBoxLayout(workspace)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QFrame()
        header.setObjectName("pageHeader")
        header.setFixedHeight(64)
        heading = QHBoxLayout(header)
        heading.setContentsMargins(24, 0, 24, 0)
        self.page_title = QLabel()
        self.page_title.setObjectName("pageTitle")
        heading.addWidget(self.page_title, 1)
        outer.addWidget(header)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        root.addWidget(workspace, 1)
        self.download_page = self._downloads_page()
        self.settings_page = settings_page(self)
        self.about_page = about_page(self)
        for page in (self.download_page, self.settings_page, self.about_page):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(650)
        self.preview_timer.timeout.connect(self._analyze_input)
        self.input.textChanged.connect(self._input_changed)
        self.input.returnPressed.connect(self._add_urls)
        self._setup_tray()
        self.settings_loading = False
        self._translate()
        self._apply_appearance()
        self._navigate(0)
        scheduler.changed.connect(self._task_changed)
        scheduler.removed.connect(self._task_removed)
        if hasattr(scheduler, "queue_finished"):
            scheduler.queue_finished.connect(self._queue_finished)
        for task in scheduler.tasks.values():
            if not task.hidden:
                self._task_changed(task)
        self._queue_status()
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._system_theme_changed)

    def _label(self, key, style=""):
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setObjectName(style)
        self.texts.append((label, key))
        return label

    def _button(self, key, callback, primary=False, icon=""):
        button = QPushButton()
        button.setMinimumHeight(32)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIconSize(QSize(18, 18))
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        self.texts.append((button, key))
        if icon:
            self.icon_buttons.append((button, icon, primary))
        return button

    @staticmethod
    def _page():
        page = QWidget()
        page.setObjectName("page")
        page.setMaximumWidth(1472)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        return page, layout

    def _downloads_page(self):
        return downloads_page(self)

    def _translate(self):
        lang = self.preferences.language
        for widget, key in self.texts:
            widget.setText(tr(lang, key))
        for combo, keys in ((self.theme, ("system", "dark", "light")), (self.name_style, ("title_name", "artist_title")),
                            (self.subfolders, ("none", "by_source", "by_author", "by_playlist"))):
            combo.blockSignals(True)
            for index, key in enumerate(keys):
                combo.setItemText(index, tr(lang, key))
            combo.blockSignals(False)
        self.input.setAccessibleName(tr(lang, "link"))
        self.page_title.setText(tr(lang, ("downloads", "settings", "about")[max(0, self.stack.currentIndex())]))
        self.format_picker.render()
        self._sync_disclosure()
        self.version_label.setText(f"{tr(lang, 'version')} {__version__}")
        for task in self.scheduler.tasks.values():
            if task.id in self.cards:
                self.cards[task.id].render(task)
        for action, key in ((self.show_action, "show_window"), (self.quit_action, "exit")):
            action.setText(tr(lang, key))
        self._render_preview()
        self._queue_status()

    def _apply_appearance(self):
        c = palette(self.preferences.theme)
        self.setStyleSheet(stylesheet(self.preferences.theme))
        input_colors = self.input.palette()
        input_colors.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["muted"]))
        self.input.setPalette(input_colors)
        for combo in self.findChildren(QComboBox):
            if not combo.property("desktopDelegate"):
                combo.setItemDelegate(QStyledItemDelegate(combo))
                combo.setProperty("desktopDelegate", True)
            colors = combo.palette()
            colors.setColor(QPalette.ColorRole.Highlight, QColor(c["tint"]))
            colors.setColor(QPalette.ColorRole.HighlightedText, QColor(c["accent"]))
            colors.setColor(QPalette.ColorRole.Accent, QColor(c["accent"]))
            for role, key in ((QPalette.ColorRole.Window, "surface"), (QPalette.ColorRole.Base, "surface"),
                              (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.WindowText, "text"),
                              (QPalette.ColorRole.Light, "border"), (QPalette.ColorRole.Dark, "border")):
                colors.setColor(role, QColor(c[key]))
            combo.view().setPalette(colors)
            combo.view().window().setPalette(colors)
        for button, name, primary in self.icon_buttons:
            button.setIcon(svg_icon(name, c["on_accent"] if primary else c["muted"]))
        for label, _name in self.site_icons:
            label.set_color(c["text"])
        self.media_preview.update()
        self.format_picker.render()
        self._sync_disclosure()
        for task_id, card in self.cards.items():
            card.render(self.scheduler.tasks[task_id])

    def _system_theme_changed(self, *_):
        if self.preferences.theme == "system":
            self._apply_appearance()

    def _navigate(self, index):
        self.nav_buttons[index].setChecked(True)
        self.stack.setCurrentIndex(index)
        self.page_title.setText(tr(self.preferences.language, ("downloads", "settings", "about")[index]))

    def _input_changed(self):
        self.preview_timer.stop()
        self._cancel_preview()
        self.preview_task = None
        self.selected_task_id = ""
        self.format_picker.set_task(None)
        self.format_picker.setEnabled(True)
        self.format_picker.modes.setEnabled(True)
        self.source_panel.hide()
        self.media_preview.set_task(None)
        self.media_preview.hide()
        self.options_editor.set_task(None)
        self.preview_advanced.setEnabled(False)
        self.parameter_fields.hide()
        self.options_popup.hide()
        self.input_error.hide()
        valid, invalid = parse_urls(self.input.text())
        self.add_button.setText(tr(self.preferences.language, "download_now"))
        self.add_button.setEnabled(len(valid) > 1 and not invalid)
        self._composer_state("batch" if len(valid) > 1 and not invalid else "loading" if len(valid) == 1 and not invalid else "empty")
        if len(valid) == 1 and not invalid:
            self.preview_timer.start()

    def _composer_state(self, state):
        ready = state == "ready"
        self.empty_hint.setVisible(state == "empty")
        self.loading_panel.setVisible(state == "loading")
        self.analysis_status.setVisible(state == "loading")
        self.source_layout.setVisible(ready)
        self.format_picker.modes.setVisible(ready)
        self.parameter_fields.setVisible(ready)
        self.add_button.setVisible(ready or state == "batch")
        if not ready:
            self.options_popup.hide()

    def _cancel_preview(self):
        self.source_probe.cancel()
        job, self.preview_job = self.preview_job, None
        if job:
            job.cancel()
        self.analysis_bar.hide()

    def _analyze_input(self):
        valid, invalid = parse_urls(self.input.text())
        if len(valid) != 1 or invalid or self.closing:
            return
        self._cancel_preview()
        self.preview_url = valid[0]
        self.input_error.hide()
        task = Task(valid[0], folder=self.preferences.folder)
        try:
            job = EngineJob(task, self.scheduler.tools, self.preferences, "metadata", self)
        except KeyError:
            self._input_failure("error_engine_missing")
            return
        self.preview_job = job
        self.preview_jobs.append(job)
        job.metadata_ready.connect(lambda _id, info, current=job: self._preview_ready(current, task, info))
        job.failed.connect(lambda _id, error, current=job: self._preview_failed(current, error))
        job.finished.connect(lambda _id, current=job: self._preview_finished(current))
        self._composer_state("loading")
        self.media_preview.set_task(None)
        job.start()

    def _preview_ready(self, job, task, info):
        if job is not self.preview_job or self.closing:
            return
        populate_task(task, info)
        if not task.playlist and not available_selections({"formats": task.formats}):
            self._input_failure("error_no_formats")
            return
        task.state = State.READY
        task.selection = default_selection(task, self.preferences)
        self.preview_task = task
        self.analysis_bar.hide()
        self.format_picker.set_task(task)
        self._render_preview()
        self.source_probe.start(task)

    def _source_probe_ready(self, task):
        if not self.closing and task is self.preview_task:
            self._render_source_facts(task)
            if self.options_editor.task is task:
                self.options_editor.end.setPlaceholderText(self.options_editor._time(task.duration))
            self.media_preview.set_task(task)

    def _preview_failed(self, job, error):
        if job is self.preview_job and error != "cancelled":
            self._input_failure(error)

    def _preview_finished(self, job):
        if job in self.preview_jobs:
            self.preview_jobs.remove(job)
        if job is self.preview_job:
            self.preview_job = None
        job.deleteLater()

    def _input_failure(self, error):
        self._composer_state("error")
        self.analysis_bar.hide()
        self.source_panel.hide()
        self.media_preview.hide()
        self.input_error.setText(tr(self.preferences.language, error))
        self.input_error.show()
        self.add_button.setEnabled(False)

    def _render_preview(self):
        task = self.preview_task or self.scheduler.tasks.get(self.selected_task_id)
        if not task:
            return
        self._composer_state("ready")
        self.source_panel.show()
        self.media_preview.show()
        self.media_preview.set_task(task)
        self.source_title.setText(task.title)
        self.source_title.setToolTip(f"{task.title}\n{task.url}")
        lang = self.preferences.language
        site = next((name for name in ("YouTube", "Facebook", "Instagram", "TikTok", "SoundCloud") if name.casefold() in task.source.casefold()), task.source)
        if task.source.casefold() in {"twitter", "x"}:
            site = "X (Twitter)"
        self.source_name.setText(site)
        names = {"YouTube": "youtube", "Facebook": "facebook", "Instagram": "instagram", "TikTok": "tiktok", "SoundCloud": "soundcloud", "X (Twitter)": "x-twitter"}
        icon = svg_icon(names[site], palette(self.preferences.theme)["muted"], site=True) if site in names else svg_icon("link", palette(self.preferences.theme)["muted"])
        self.source_icon.setPixmap(icon.pixmap(QSize(22, 22), self.devicePixelRatioF()))
        self.source_details.setText(f"{tr(lang, 'author')}: {task.author}" if task.author else "")
        self.source_details.setToolTip(task.author)
        self.source_details.setVisible(bool(task.author))
        self._render_source_facts(task)
        editable = task.state in {State.READY, State.FAILED, State.CANCELLED, State.INTERRUPTED}
        self.preview_advanced.setEnabled(editable and not task.playlist)
        self.parameter_fields.setVisible(not task.playlist)
        if self.format_picker.task is not task or self.format_picker.selection != task.selection:
            self.format_picker.set_task(task)
        self.format_picker.setVisible(not task.playlist)
        self.format_picker.modes.setVisible(not task.playlist)
        self.format_picker.setEnabled(editable)
        self.format_picker.modes.setEnabled(editable)
        self.options_editor.set_task(task)
        self.options_editor.setEnabled(editable)
        self._sync_disclosure()
        self.add_button.setEnabled(self.preview_task is not None)

    def _render_source_facts(self, task):
        lang = self.preferences.language
        self.source_duration.setText(f"{int(task.duration)//60}:{int(task.duration)%60:02}" if task.duration is not None else "—")
        estimated = estimate_size(task)
        if task.state == State.COMPLETED and task.final_path:
            try:
                estimated = Path(task.final_path).stat().st_size
            except OSError:
                pass
        from .task_card import size_label
        self.source_size.setText(("" if task.state == State.COMPLETED else "≈ ") + size_label(estimated, lang) if estimated else "—")

    def _composer_selection(self, selection):
        task = self.preview_task or self.scheduler.tasks.get(self.selected_task_id)
        if task and task.id in self.scheduler.tasks:
            task.output_stem = ""
            task.naming_version = 2
            self.scheduler._save(task)
        self._remember_selection(selection)
        self._render_preview()

    def _remember_selection(self, selection):
        if selection.startswith("mp3:"):
            self.preferences.media_mode = "audio"
            self.preferences.audio_format = "mp3"
            self.preferences.mp3_bitrate = int(selection.split(":")[1])
        elif selection in {"audio", "m4a"}:
            self.preferences.media_mode = "audio"
            self.preferences.audio_format = selection
        else:
            self.preferences.media_mode = "video"
            self.preferences.video_quality = selection
        try:
            self.preferences.save()
        except OSError as exc:
            self.input_error.setText(str(exc))
            self.input_error.show()

    def _add_urls(self, *_args, download=True):
        valid, invalid = parse_urls(self.input.text())
        if invalid or not valid:
            self._input_failure("invalid_links")
            return
        if len(valid) > 1:
            for url in valid:
                self.scheduler.add(url, download=True)
            self._navigate(0)
            return
        if not self.preview_task or self.preview_task.url != valid[0]:
            self.preview_timer.stop()
            self._analyze_input()
            return
        if not self.options_editor.apply():
            self.preview_advanced.setChecked(True)
            return
        task = Task.from_dict(self.preview_task.to_dict())
        task.id = uuid4().hex
        if task.playlist:
            if not self._expand_playlist(task):
                return
        else:
            if not self._submit(task):
                return
        self._navigate(0)

    def _submit(self, task):
        if not self._confirm_duplicate(task):
            return False
        task.folder = self.preferences.folder
        self.scheduler.tasks[task.id] = task
        self.selected_task_id = task.id
        self.scheduler._save(task)
        self.start_task(task.id)
        return True

    def _confirm_duplicate(self, task):
        duplicate = None if task.repeat else self.scheduler.find_duplicate(task)
        if not duplicate:
            return True
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr(self.preferences.language, "duplicate"))
        dialog.setText(task.title or task.url)
        again = dialog.addButton(tr(self.preferences.language, "download_again"), QMessageBox.ButtonRole.AcceptRole)
        opened = dialog.addButton(tr(self.preferences.language, "open"), QMessageBox.ButtonRole.ActionRole) if duplicate.final_path and Path(duplicate.final_path).is_file() else None
        cancel = dialog.addButton(tr(self.preferences.language, "cancel"), QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        dialog.exec()
        if opened and dialog.clickedButton() is opened:
            self.open_result(duplicate.id, False)
        if dialog.clickedButton() is again:
            task.repeat = True
            return True
        return False

    def _sync_disclosure(self):
        lang, colors = self.preferences.language, palette(self.preferences.theme)
        checked = self.preview_advanced.isChecked()
        task = self.preview_task or self.scheduler.tasks.get(self.selected_task_id)
        audio = bool(task and (task.selection in {"audio", "m4a"} or task.selection.startswith("mp3:")))
        self.advanced_caption.setText(tr(lang, "clip_toggle" if audio else "fragment_tracks"))
        summary = tr(lang, "configure")
        if task and (task.clip_start is not None or task.clip_end is not None):
            summary = f"{tr(lang, 'clip_toggle')} · {self.options_editor._time(task.clip_start or 0)}–{self.options_editor._time(task.clip_end) or '…'}"
        self.preview_advanced.setText(summary)
        self.preview_advanced.setIcon(svg_icon("more", colors["muted"]))
        self.preview_advanced.chevron = svg_icon("chevronUp" if checked else "chevron", colors["muted"])
        self.preview_advanced.update()

    def _preview_options(self, *_):
        self._sync_disclosure()
        if self.preview_advanced.isChecked():
            self.options_popup.show_below()
        else:
            self.options_popup.hide()

    def _dismiss_preview_options(self):
        self.preview_advanced.setChecked(False)
        self.options_editor.set_task(self.preview_task or self.scheduler.tasks.get(self.selected_task_id))

    def _apply_preview_options(self):
        if self.options_editor.apply():
            self._preview_options_changed()
            self.options_popup.hide()
        else:
            self.options_popup.show_below()

    def _preview_options_changed(self):
        task = self.preview_task or self.scheduler.tasks.get(self.selected_task_id)
        if task and task.state in {State.READY, State.FAILED, State.CANCELLED, State.INTERRUPTED} and self.options_editor.apply():
            self.format_picker.set_task(task)
            if task.id in self.scheduler.tasks:
                self.scheduler._save(task)
            self._render_preview()

    def edit_options(self, task):
        from .task_options import TaskOptionsDialog
        dialog = TaskOptionsDialog(task, self.preferences, self)
        if dialog.exec():
            if task is self.preview_task:
                self.format_picker.set_task(task)
            if task.id in self.scheduler.tasks:
                self.scheduler._save(task)

    def _expand_playlist(self, task):
        from .task_options import PlaylistDialog
        dialog = PlaylistDialog(task, self.preferences.language, self)
        if dialog.exec():
            for entry in dialog.selected_entries():
                child = self.scheduler.add(entry["url"], download=True)
                child.playlist_title = task.title
                child.playlist_index = entry["index"]
                self.scheduler._save(child)
            return True
        return False

    def _download_all(self):
        for task in list(self.scheduler.tasks.values()):
            if task.state == State.READY:
                self.start_task(task.id)

    def start_task(self, task_id):
        task = self.scheduler.tasks[task_id]
        if task.playlist:
            if self._expand_playlist(task):
                self.scheduler.remove(task.id)
            return
        if not self._confirm_duplicate(task):
            return
        self.scheduler.enqueue(task_id)

    def select_task(self, task_id):
        if task_id not in self.scheduler.tasks:
            return
        self.preview_timer.stop()
        self._cancel_preview()
        self.selected_task_id = task_id
        self.input.blockSignals(True)
        self.input.setText(self.scheduler.tasks[task_id].url)
        self.input.blockSignals(False)
        self.preview_task = None
        if self.scheduler.tasks[task_id].state == State.COMPLETED:
            self.preview_task = replace(self.scheduler.tasks[task_id], id=uuid4().hex, state=State.READY, final_path="", final_paths=[],
                                        output_stem="", folder_configured=False, repeat=False)
        self.input_error.hide()
        self._render_preview()
        for ident, card in self.cards.items():
            card.setProperty("selected", ident == task_id)
            card.style().unpolish(card)
            card.style().polish(card)
        self._navigate(0)

    def _task_changed(self, task):
        if task.hidden or self.closing:
            return
        if task.id not in self.cards:
            self.cards[task.id] = TaskCard(task, self)
            (self.cards_layout if task.state == State.COMPLETED else self.active_layout).addWidget(self.cards[task.id])
        else:
            self.cards[task.id].render(task)
        card = self.cards[task.id]
        if task.thumbnail.startswith("https://") and not card.thumbnail_requested:
            card.thumbnail_requested = True
            self._request_thumbnail(task.thumbnail, card.thumbnail, (64, 44))
        if task.id == self.selected_task_id and not self.preview_task:
            self._render_preview()
        self._queue_status()

    def _request_thumbnail(self, url, label, size):
        from shiboken6 import isValid
        label.setProperty("thumbnailUrl", url)
        def finished(pixmap):
            if isValid(label) and label.property("thumbnailUrl") == url and not pixmap.isNull():
                ratio = label.devicePixelRatioF()
                scaled = pixmap.scaled(round(size[0] * ratio), round(size[1] * ratio), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                scaled.setDevicePixelRatio(ratio)
                label.setPixmap(scaled)
        self.images.fetch(url, finished)

    def _task_removed(self, task_id):
        card = self.cards.pop(task_id, None)
        if card:
            self.cards_layout.removeWidget(card)
            self.active_layout.removeWidget(card)
            card.deleteLater()
        self._queue_status()
        if self.selected_task_id == task_id:
            self.selected_task_id = ""
            self._input_changed()

    def _queue_status(self):
        tasks = [task for task in self.scheduler.tasks.values() if not task.hidden]
        ready = sum(task.state == State.READY for task in tasks)
        busy = sum(task.state in BUSY for task in tasks)
        finished = [task for task in tasks if task.state == State.COMPLETED]
        active = [task for task in tasks if task.state != State.COMPLETED]
        self.active_panel.setVisible(bool(active))
        self.completed_panel.setVisible(bool(finished))
        self.all_button.setVisible(ready > 1)
        self.stop_button.setVisible(busy > 1)
        for button, key in ((self.all_button, "all"), (self.stop_button, "stop_all")):
            button.setText("")
            button.setToolTip(tr(self.preferences.language, key))
            button.setAccessibleName(tr(self.preferences.language, key))
        self.clear_button.setVisible(bool(finished))
        running = sum(task.state in {State.FETCHING_METADATA, State.DOWNLOADING, State.POSTPROCESSING} for task in active)
        waiting = sum(task.state in {State.PENDING_METADATA, State.QUEUED} for task in active)
        lang = self.preferences.language
        self.queue_summary.setText(" · ".join(part for part in (
            f"{tr(lang, 'active_count')}: {running}" if running else "", f"{tr(lang, 'waiting_count')}: {waiting}" if waiting else "") if part))
        active.sort(key=lambda task: task.created_at)
        active.sort(key=lambda task: task.state in {State.PENDING_METADATA, State.QUEUED, State.CANCELLED, State.FAILED, State.INTERRUPTED})
        finished.sort(key=lambda task: task.created_at, reverse=True)
        for target, ordered in ((self.active_layout, active), (self.cards_layout, finished)):
            for index, task in enumerate(ordered):
                card = self.cards.get(task.id)
                if card:
                    other = self.cards_layout if target is self.active_layout else self.active_layout
                    other.removeWidget(card)
                    if target.indexOf(card) != index:
                        target.insertWidget(index, card)

    def _stop_all(self):
        self.scheduler.cancel_all()

    def _clear_completed(self):
        for task in list(self.scheduler.tasks.values()):
            if not task.hidden and task.state == State.COMPLETED and task.id not in self.scheduler.jobs:
                self.scheduler.remove(task.id)

    def open_result(self, task_id, folder):
        path = Path(self.scheduler.tasks[task_id].final_path)
        if path.is_file():
            if folder:
                open_local(path)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _choose_folder(self):
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, tr(self.preferences.language, "path"), self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)
            self._save_settings()

    def _save_settings(self, *_):
        if self.settings_loading:
            return True
        from al_media.config import validate_folder
        try:
            candidate = replace(self.preferences, folder=str(validate_folder(self.path_edit.text())), theme=self.theme.currentData(),
                                language=self.language.currentData(), concurrency=self.concurrency.value(), name_style=self.name_style.currentData(),
                                subfolders=self.subfolders.currentData(), music_tags=self.music_tags.isChecked(), music_cover=self.music_cover.isChecked())
            candidate.close_to_tray = self.close_to_tray.isChecked()
            candidate.save()
            for key, value in asdict(candidate).items():
                setattr(self.preferences, key, value)
            self._translate()
            self._apply_appearance()
            self.scheduler.pump()
            return True
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, tr(self.preferences.language, "settings"), str(exc))
            return False

    def _show_licenses(self):
        path = app_root() / "THIRD_PARTY_NOTICES.md"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        self.show_action = QAction(self)
        self.quit_action = QAction(self)
        self.show_action.triggered.connect(self._show_window)
        self.quit_action.triggered.connect(self._exit_application)
        menu.addAction(self.show_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self._show_window() if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick} else None)
        available = QSystemTrayIcon.isSystemTrayAvailable()
        if available:
            self.tray.show()

    def _show_window(self):
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def _minimize_to_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
            self.hide()

    def _exit_application(self):
        self.explicit_exit = True
        if not self.close():
            self.explicit_exit = False

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "media_preview"):
            self.media_preview.sync_animation()

    def _queue_finished(self, completed, failed):
        if self.tray.isVisible() and not self.isActiveWindow():
            self.tray.showMessage(tr(self.preferences.language, "queue_finished"),
                                  tr(self.preferences.language, "queue_result").format(completed=completed, failed=failed))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        values = []
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".txt"):
                try:
                    values.append(Path(url.toLocalFile()).read_text(encoding="utf-8-sig"))
                except (OSError, UnicodeError):
                    self._input_failure("file_read_error")
            elif url.scheme() in {"http", "https"}:
                values.append(url.toString())
        if not values and event.mimeData().hasText():
            values.append(event.mimeData().text())
        if values:
            self.input.setText("\n".join(values))
            self._navigate(0)
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.preferences.close_to_tray and not self.explicit_exit and QSystemTrayIcon.isSystemTrayAvailable():
            self._minimize_to_tray()
            event.ignore()
            return
        if self.scheduler.jobs and QMessageBox.question(self, tr(self.preferences.language, "exit"), tr(self.preferences.language, "exit_jobs")) != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        self.closing = True
        self.source_probe.shutdown()
        if self.media_preview.extractor:
            self.media_preview.extractor.shutdown()
        self.preview_timer.stop()
        self._cancel_preview()
        self.scheduler.shutdown()
        for job in [*self.scheduler.jobs.values(), *self.preview_jobs]:
            job.cancel()
            job.process.waitForFinished(3000)
        self.tray.hide()
        event.accept()
