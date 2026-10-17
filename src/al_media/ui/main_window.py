from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from al_media import APP_FULL_NAME, APP_NAME, __version__
from al_media.config import Preferences, app_root, data_root
from al_media.core.metadata import parse_urls
from al_media.core.scheduler import Scheduler
from al_media.core.tools import bundled_tools
from al_media.i18n import format_label, tr
from al_media.models import State, Task

from .task_card import BUSY, TaskCard
from .themes import stylesheet


class UrlInput(QTextEdit):
    entered = Signal()

    def keyPressEvent(self, event: object) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.entered.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, scheduler: Scheduler, preferences: Preferences, probe_tools: bool = True):
        super().__init__()
        self.scheduler, self.preferences = scheduler, preferences
        self.cards: dict[str, TaskCard] = {}
        self.network = QNetworkAccessManager(self)
        self.installing = False
        self.texts = []
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(app_root() / "assets" / "app.ico")))
        self.resize(1180, 800)
        self.setMinimumSize(940, 640)
        self.setAcceptDrops(True)
        shell = QWidget()
        shell.setObjectName("shell")
        self.setCentralWidget(shell)
        root = QVBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        top = QFrame()
        top.setObjectName("topbar")
        top_row = QHBoxLayout(top)
        top_row.setContentsMargins(20, 15, 20, 15)
        brand_box = QWidget()
        brand_box.setFixedWidth(180)
        brand_row = QHBoxLayout(brand_box)
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(10)
        brand_icon = QLabel()
        brand_icon.setPixmap(self.windowIcon().pixmap(28, 28))
        brand_row.addWidget(brand_icon)
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        brand_row.addWidget(brand)
        brand_row.addStretch()
        top_row.addWidget(brand_box)
        self.input = UrlInput()
        self.input.setAcceptRichText(False)
        self.input.setFixedHeight(44)
        self.input.entered.connect(self._add_urls)
        top_row.addWidget(self.input, 1)
        self.paste_button = self._button("paste", self._paste)
        top_row.addWidget(self.paste_button)
        self.quality_button = self._button("choose_quality", lambda: self._add_urls(download=False))
        top_row.addWidget(self.quality_button)
        self.add_button = self._button("download_now", self._add_urls, primary=True)
        top_row.addWidget(self.add_button)
        root.addWidget(top)
        outer = QHBoxLayout()
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(195)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 20, 12, 18)
        self.nav = QListWidget()
        self.nav.setObjectName("navigation")
        self.nav.setSpacing(4)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.currentRowChanged.connect(self._navigate)
        side.addWidget(self.nav)
        side.addWidget(self._label("local_app", "muted"))
        version = QLabel(f"v{__version__}  ·  yt-dlp")
        version.setObjectName("muted")
        side.addWidget(version)
        outer.addWidget(sidebar)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        root.addLayout(outer, 1)

        self.download_page, dl = self._page("downloads", "downloads_hint")
        title_row = QHBoxLayout()
        self.queue_summary = QLabel()
        self.queue_summary.setObjectName("muted")
        title_row.addWidget(self.queue_summary, 1)
        self.import_button = self._button("import_links", self._import_links)
        title_row.addWidget(self.import_button)
        dl.addLayout(title_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("scrollBody")
        self.cards_layout = QVBoxLayout(body)
        self.cards_layout.setContentsMargins(0, 0, 8, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.empty_panel = QFrame()
        self.empty_panel.setObjectName("panel")
        empty = QVBoxLayout(self.empty_panel)
        empty.setContentsMargins(28, 55, 28, 55)
        empty.setSpacing(18)
        empty_icon = QLabel()
        empty_icon.setPixmap(self.windowIcon().pixmap(64, 64))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(empty_icon)
        self.empty_label = self._label("empty", "sectionTitle")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(self.empty_label)
        hint = self._label("empty_hint", "muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(hint)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self._button("paste", self._paste, primary=True))
        actions.addWidget(self._button("import_links", self._import_links))
        actions.addStretch()
        empty.addLayout(actions)
        sites = QLabel("YouTube  ·  VK  ·  TikTok  ·  Vimeo  ·  Instagram")
        sites.setObjectName("muted")
        sites.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(sites)
        self.cards_layout.addWidget(self.empty_panel)
        scroll.setWidget(body)
        dl.addWidget(scroll, 1)
        footer = QHBoxLayout()
        self.all_button = self._button("all", self._download_all, primary=True)
        self.stop_button = self._button("stop_all", self._stop_all)
        self.clear_button = self._button("clear_completed", self._clear_completed)
        footer.addWidget(self.all_button)
        footer.addWidget(self.stop_button)
        footer.addWidget(self.clear_button)
        footer.addStretch()
        footer.addWidget(self._button("destination", self._open_downloads))
        dl.addLayout(footer)
        self.stack.addWidget(self.download_page)

        self.history_page, history = self._page("history", "history_hint")
        self.history_search = QLineEdit()
        self.history_search.textChanged.connect(self._refresh_history)
        history.addWidget(self.history_search)
        self.history_list = QListWidget()
        self.history_list.setSpacing(4)
        self.history_list.itemDoubleClicked.connect(self._open_history_item)
        history.addWidget(self.history_list, 1)
        self.history_empty = self._label("history_empty", "muted")
        history.addWidget(self.history_empty)
        history_actions = QHBoxLayout()
        history_actions.addWidget(self._button("open", lambda: self._history_open(False)))
        history_actions.addWidget(self._button("folder", lambda: self._history_open(True)))
        history_actions.addStretch()
        history.addLayout(history_actions)
        self.stack.addWidget(self.history_page)

        self.settings_page, settings = self._page("settings", "settings_hint")
        self.settings_page.setMaximumWidth(1050)
        general, form = self._form_panel(settings, "general")
        self.path_edit = QLineEdit(preferences.folder)
        self.choose_button = self._button("choose", self._choose_folder)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(self.choose_button)
        form.addRow(self._label("path"), path_row)
        self.theme = QComboBox()
        for key in ("dark", "light"):
            self.theme.addItem(tr(preferences.language, key), key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(preferences.theme)))
        self.language = QComboBox()
        for name, key in (("Русский", "ru"), ("English", "en"), ("Українська", "uk")):
            self.language.addItem(name, key)
        self.language.setCurrentIndex(max(0, self.language.findData(preferences.language)))
        appearance = QHBoxLayout()
        appearance.addWidget(self.theme)
        appearance.addWidget(self.language)
        form.addRow(self._label("appearance"), appearance)

        save_row = QHBoxLayout()
        self.save_button = self._button("save", self._save_settings, primary=True)
        save_row.addWidget(self.save_button)
        self.save_status = QLabel()
        self.save_status.setObjectName("muted")
        save_row.addWidget(self.save_status, 1)
        settings.addStretch()
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setWidget(self.settings_page)
        settings_wrapper = QWidget()
        settings_outer = QVBoxLayout(settings_wrapper)
        settings_outer.setContentsMargins(0, 0, 0, 0)
        settings_outer.addWidget(self.settings_scroll, 1)
        save_row.setContentsMargins(26, 8, 22, 22)
        settings_outer.addLayout(save_row)
        self.stack.addWidget(settings_wrapper)

        self.about_page, about = self._page("about", "about_hint")
        panel = QFrame()
        panel.setObjectName("panel")
        content = QVBoxLayout(panel)
        content.setContentsMargins(28, 28, 28, 28)
        about_icon = QLabel()
        about_icon.setPixmap(self.windowIcon().pixmap(80, 80))
        content.addWidget(about_icon, 0, Qt.AlignmentFlag.AlignLeft)
        title = QLabel(APP_NAME)
        title.setObjectName("pageTitle")
        content.addWidget(title)
        full_name = QLabel(APP_FULL_NAME)
        full_name.setObjectName("muted")
        content.addWidget(full_name)
        version = QLabel(f"v{__version__}")
        version.setObjectName("badge")
        content.addWidget(version, 0, Qt.AlignmentFlag.AlignLeft)
        content.addWidget(self._label("about_description", "muted"))
        tools = bundled_tools()
        missing = [name for name, path in tools.items() if not path.is_file()]
        self.tool_status = self._label("tools_missing" if missing else "tools_ready", "muted")
        if missing:
            self.tool_status.setToolTip(", ".join(missing))
        content.addWidget(self.tool_status)
        self.logs_button = self._button("logs", self._open_logs)
        content.addWidget(self.logs_button, 0, Qt.AlignmentFlag.AlignLeft)
        about.addWidget(panel)
        about.addStretch()
        self.stack.addWidget(self.about_page)
        self._translate()
        self.nav.setCurrentRow(0)
        self.setStyleSheet(stylesheet(preferences.theme))
        scheduler.changed.connect(self._task_changed)
        scheduler.removed.connect(self._task_removed)
        for task in reversed(list(scheduler.tasks.values())):
            if not task.hidden:
                self._task_changed(task)
        self._queue_status()

    def _label(self, key, style=""):
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setObjectName(style)
        self.texts.append((label, key))
        return label

    def _button(self, key, callback, primary=False):
        button = QPushButton()
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        self.texts.append((button, key))
        return button

    def _page(self, title, hint):
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 22, 22)
        layout.setSpacing(14)
        layout.addWidget(self._label(title, "pageTitle"))
        layout.addWidget(self._label(hint, "muted"))
        return page, layout

    def _form_panel(self, layout, title):
        panel = QFrame()
        panel.setObjectName("panel")
        inside = QVBoxLayout(panel)
        inside.setContentsMargins(20, 18, 20, 18)
        inside.setSpacing(14)
        inside.addWidget(self._label(title, "sectionTitle"))
        form = QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        inside.addLayout(form)
        layout.addWidget(panel)
        return panel, form

    def _translate(self):
        language = self.preferences.language
        for form in self.settings_page.findChildren(QFormLayout):
            for row in range(form.rowCount()):
                item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if item and isinstance(item.widget(), QLabel):
                    item.widget().setFixedWidth(175)
        for widget, key in self.texts:
            widget.setText(tr(language, key))
        for index, key in enumerate(("downloads", "history", "settings", "about")):
            if self.nav.count() <= index:
                self.nav.addItem(tr(language, key))
            else:
                self.nav.item(index).setText(tr(language, key))
        self.input.setPlaceholderText(tr(language, "input_hint"))
        self.input.setAccessibleName(tr(language, "input_hint"))
        self.history_search.setPlaceholderText(tr(language, "search_history"))
        for index in range(self.theme.count()):
            self.theme.setItemText(index, tr(language, self.theme.itemData(index)))
        for task in self.scheduler.tasks.values():
            if task.id in self.cards:
                self.cards[task.id].render(task)
        self._queue_status()

    def _navigate(self, index: int) -> None:
        if index >= 0:
            self.stack.setCurrentIndex(index)
            if index == 1:
                self._refresh_history()

    def _paste(self) -> None:
        from PySide6.QtWidgets import QApplication
        self.input.setPlainText(QApplication.clipboard().text())
        self.input.setFocus()

    def _add_urls(self, _checked=False, *, download=True) -> None:
        if self.installing:
            return
        valid, invalid = parse_urls(self.input.toPlainText())
        if invalid or not valid:
            QMessageBox.warning(self, "URL", tr(self.preferences.language, "invalid_links"))
        for url in valid:
            self.scheduler.add(url, download=download)
        if valid:
            self.input.setPlainText("\n".join(invalid))
            self.nav.setCurrentRow(0)

    def _download_all(self) -> None:
        for task in self.scheduler.tasks.values():
            if task.state == State.READY:
                self.start_task(task.id)

    def _task_changed(self, task: Task) -> None:
        if task.hidden:
            return
        if task.id not in self.cards:
            self.cards[task.id] = TaskCard(task, self)
            self.cards_layout.addWidget(self.cards[task.id])
        else:
            self.cards[task.id].render(task)
        if task.thumbnail.startswith("https://") and not self.cards[task.id].thumbnail_requested and task.state == State.READY:
            self.cards[task.id].thumbnail_requested = True
            request = QNetworkRequest(QUrl(task.thumbnail))
            request.setTransferTimeout(10000)
            reply = self.network.get(request)
            reply.finished.connect(lambda ident=task.id, current=reply: self._thumbnail(ident, current))
        if task.state == State.COMPLETED:
            self._refresh_history()
        self._queue_status()

    def _thumbnail(self, task_id: str, reply: object) -> None:
        from PySide6.QtGui import QPixmap
        if task_id in self.cards and reply.error() == reply.NetworkError.NoError:
            image = QPixmap()
            if image.loadFromData(reply.readAll()) and image.width() <= 4096 and image.height() <= 4096:
                self.cards[task_id].thumbnail.setPixmap(image.scaled(128, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        reply.deleteLater()

    def _task_removed(self, task_id: str) -> None:
        card = self.cards.pop(task_id, None)
        if card:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._queue_status()
        self._refresh_history()

    def start_task(self, task_id: str) -> None:
        if self.installing:
            return
        task = self.scheduler.tasks[task_id]
        if task.playlist and task.state == State.READY:
            count = task.playlist_count or 0
            response = QMessageBox.question(self, "Playlist / Плейлист",
                f"Download entire playlist ({count} items)? / Скачать весь плейлист ({count})?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if response == QMessageBox.StandardButton.Cancel:
                return
            if response == QMessageBox.StandardButton.No:
                if task.playlist_first_url:
                    self.scheduler.add(task.playlist_first_url, download=True)
                    self.scheduler.remove(task.id)
                else:
                    QMessageBox.information(self, "Playlist", "A direct video URL is unavailable; paste a video link / Прямая ссылка на видео недоступна; вставьте ссылку на видео")
                return
            if count > 100 and QMessageBox.question(self, "Large playlist", f"Confirm {count} items / Подтвердите {count} элементов") != QMessageBox.StandardButton.Yes:
                return
        self.scheduler.enqueue(task_id)

    def open_result(self, task_id: str, folder: bool) -> None:
        path = Path(self.scheduler.tasks[task_id].final_path)
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent if folder else path)))

    def _refresh_history(self):
        selected = self.history_list.currentItem()
        selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.history_list.clear()
        query = self.history_search.text().strip().casefold()
        for task in sorted(self.scheduler.tasks.values(), key=lambda task: task.created_at, reverse=True):
            if task.state != State.COMPLETED or query not in f"{task.title} {task.source} {task.final_path}".casefold():
                continue
            try:
                date = datetime.fromisoformat(task.created_at).astimezone().strftime("%d.%m.%Y %H:%M")
            except ValueError:
                date = task.created_at
            item = QListWidgetItem(f"{task.title}\n{date}  ·  {task.source}  ·  {format_label(self.preferences.language, task.selection)}")
            item.setToolTip(task.final_path)
            item.setData(Qt.ItemDataRole.UserRole, task.id)
            self.history_list.addItem(item)
            if task.id == selected_id:
                self.history_list.setCurrentItem(item)
        self.history_empty.setVisible(self.history_list.count() == 0)

    def _history_open(self, folder):
        item = self.history_list.currentItem()
        if item:
            self.open_result(item.data(Qt.ItemDataRole.UserRole), folder)

    def _open_history_item(self, item: QListWidgetItem) -> None:
        self.open_result(item.data(Qt.ItemDataRole.UserRole), False)

    def _choose_folder(self) -> None:
        value = QFileDialog.getExistingDirectory(self, tr(self.preferences.language, "path"), self.path_edit.text())
        if value:
            self.path_edit.setText(value)

    def _save_settings(self):
        from al_media.config import validate_folder
        try:
            candidate = replace(self.preferences,
                folder=str(validate_folder(self.path_edit.text())),
                theme=self.theme.currentData(), language=self.language.currentData())
            candidate.save()
            for key, value in asdict(candidate).items():
                setattr(self.preferences, key, value)
            self.setStyleSheet(stylesheet(self.preferences.theme))
            self._translate()
            self.save_status.setText(tr(self.preferences.language, "saved"))
            self.scheduler.pump()
            return True
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, tr(self.preferences.language, "settings"), str(exc))
            return False

    def _import_links(self):
        path, _ = QFileDialog.getOpenFileName(self, tr(self.preferences.language, "import_links"), "", "Text (*.txt)")
        if path:
            try:
                self.input.setPlainText(Path(path).read_text(encoding="utf-8-sig"))
                self._add_urls()
            except (OSError, UnicodeError):
                QMessageBox.warning(self, "TXT", tr(self.preferences.language, "file_read_error"))

    def _queue_status(self):
        tasks = [task for task in self.scheduler.tasks.values() if not task.hidden]
        active = sum(task.state in BUSY for task in tasks)
        ready = sum(task.state == State.READY for task in tasks)
        completed = sum(task.state == State.COMPLETED for task in tasks)
        self.empty_panel.setVisible(not tasks)
        self.all_button.setVisible(ready > 0)
        self.all_button.setEnabled(ready > 0)
        self.stop_button.setVisible(active > 0)
        self.stop_button.setEnabled(active > 0)
        self.clear_button.setVisible(completed > 0)
        self.clear_button.setEnabled(completed > 0)
        self.queue_summary.setText(tr(self.preferences.language, "queue_summary").format(total=len(tasks), active=active, ready=ready))

    def _stop_all(self):
        self.scheduler.cancel_all()

    def _clear_completed(self):
        for task in list(self.scheduler.tasks.values()):
            if task.state == State.COMPLETED and not task.hidden:
                self.scheduler.remove(task.id)

    def _open_downloads(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.preferences.folder))

    def _open_logs(self) -> None:
        folder = data_root() / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def dragEnterEvent(self, event: object) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: object) -> None:
        values = []
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".txt"):
                try:
                    values.append(Path(url.toLocalFile()).read_text(encoding="utf-8"))
                except (OSError, UnicodeError):
                    QMessageBox.warning(self, "TXT", tr(self.preferences.language, "file_read_error"))
            elif url.scheme() in {"http", "https"}:
                values.append(url.toString())
        if not values and event.mimeData().hasText():
            values.append(event.mimeData().text())
        if values:
            self.input.setPlainText("\n".join(values))
            self._add_urls()
        event.acceptProposedAction()

    def closeEvent(self, event: object) -> None:
        if self.scheduler.jobs:
            answer = QMessageBox.question(self, tr(self.preferences.language, "exit"), tr(self.preferences.language, "exit_jobs"))
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.scheduler.shutdown()
            for job in list(self.scheduler.jobs.values()):
                job.process.waitForFinished(3000)
        event.accept()
