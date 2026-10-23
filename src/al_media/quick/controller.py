from __future__ import annotations

from pathlib import Path
from time import monotonic

from PySide6.QtCore import Property, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QSystemTrayIcon

from al_media import APP_NAME, __version__
from al_media.config import app_root, validate_folder
from al_media.models import State

from .downloads_model import DownloadsModel
from .localization import Localization, text
from .media import MediaViewModel
from .viewmodels.composer import ComposerViewModel
from .viewmodels.settings import SettingsViewModel


class ApplicationController(QObject):
    """Composition and desktop lifecycle; no media encoding or queue rules here."""

    changed = Signal()
    focusFolder = Signal()
    returnToComposer = Signal()
    exitReady = Signal()
    duplicateRequested = Signal()
    playlistRequested = Signal()

    def __init__(self, scheduler, preferences, provider, parent=None, *, persist=True, tray=True):
        super().__init__(parent)
        self.scheduler, self.preferences = scheduler, preferences
        self._settings = SettingsViewModel(preferences, self, persist=persist)
        self._composer = ComposerViewModel(scheduler, preferences, self, persist=persist)
        self._downloads = DownloadsModel(scheduler, preferences, self)
        self._media = MediaViewModel(scheduler.tools, provider, self)
        self._localization = Localization(preferences, self)
        self._page, self._feedback = "downloads", ""
        self._pending = []
        self._duplicate_id = ""
        self._playlist = None
        self._dialog = None
        self.window = None
        self._explicit_exit = self._closing = self._exit_ready = False
        self._shutdown_started = 0
        self._shutdown_timer = QTimer(self, interval=50)
        self._shutdown_timer.timeout.connect(self._finish_shutdown)
        self._settings.preferences_changed.connect(self._preferences_changed)
        self._settings.browse_requested.connect(self.browseFolder)
        self._composer.preferences_updated.connect(self._settings.changed)
        self._composer.source_changed.connect(self._media.set_task)
        self._composer.enqueue_requested.connect(self._enqueue)
        self.scheduler.queue_finished.connect(self._queue_finished)
        self.tray = None
        self.menu = None
        self._restore_maximized = False
        if tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(str(app_root() / "assets/app.ico")), self)
            self.menu = QMenu()
            self.show_action, self.quit_action = QAction(self), QAction(self)
            self.show_action.triggered.connect(self.restore)
            self.quit_action.triggered.connect(self.quit)
            self.menu.addAction(self.show_action)
            self.menu.addSeparator()
            self.menu.addAction(self.quit_action)
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(lambda reason: self.restore() if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick} else None)
            self.tray.setToolTip(APP_NAME)
            self.tray.show()
        self._preferences_changed()

    @Property(QObject, constant=True)
    def composer(self):
        return self._composer

    @Property(QObject, constant=True)
    def settings(self):
        return self._settings

    @Property(QObject, constant=True)
    def downloads(self):
        return self._downloads

    @Property(QObject, constant=True)
    def media(self):
        return self._media

    @Property(QObject, constant=True)
    def localization(self):
        return self._localization

    @Property(str, constant=True)
    def version(self):
        return __version__

    @Property(str, constant=True)
    def logo(self):
        return QUrl.fromLocalFile(str(app_root() / "assets/app.png")).toString()

    @Property(str, constant=True)
    def licenseText(self):
        return (app_root() / "LICENSE").read_text(encoding="utf-8")

    @Property(str, constant=True)
    def noticesText(self):
        return (app_root() / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    @Property("QVariantList", constant=True)
    def licenseSections(self):
        sections = []
        for line in self.noticesText.splitlines():
            if line.startswith("- **"):
                title, _, body = line[4:].partition("**")
                sections.append({"title": title, "body": body.lstrip(": ")})
        return sections

    @Slot(str)
    def openLicenseLink(self, url):
        parsed = QUrl(url)
        if parsed.scheme() == "https":
            QDesktopServices.openUrl(parsed)

    @Property(str, notify=changed)
    def page(self):
        return self._page

    @Property(str, notify=changed)
    def feedback(self):
        return self._feedback

    @Property(bool, notify=changed)
    def closing(self):
        return self._closing

    @Property("QVariantList", notify=changed)
    def playlistEntries(self):
        return self._playlist.playlist_entries if self._playlist else []

    @Property(bool, notify=changed)
    def duplicateCanOpen(self):
        task = self.scheduler.tasks.get(self._duplicate_id)
        return bool(task and task.state == State.COMPLETED and task.final_path and Path(task.final_path).is_file())

    def _preferences_changed(self):
        self.scheduler.pump()
        self._downloads.retranslate()
        self._composer.changed.emit()
        if self.tray:
            self.show_action.setText(text(self.preferences.language, "show_window"))
            self.quit_action.setText(text(self.preferences.language, "exit"))
        self.changed.emit()

    @Slot(str)
    def navigate(self, page):
        if page not in {"downloads", "settings", "about"}:
            return
        self._page = page
        self._composer.closeRange()
        self._media.setActive(page == "downloads" and bool(self.window and self.window.isVisible()))
        self.changed.emit()

    @Slot()
    def changeFolder(self):
        self.navigate("settings")
        self.focusFolder.emit()

    @Slot()
    def back(self):
        self.navigate("downloads")
        self.returnToComposer.emit()

    def _choose(self, callback, *, initial=None):
        if self._dialog:
            return
        dialog = QFileDialog(None, text(self.preferences.language, "choose_folder"), initial or self.preferences.folder)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        if self.window:
            dialog.winId()
            dialog.windowHandle().setTransientParent(self.window)
        self._dialog = dialog

        def selected(path):
            callback(path)

        def finished(_result):
            self._dialog = None
            dialog.deleteLater()

        dialog.fileSelected.connect(selected)
        dialog.finished.connect(finished)
        dialog.open()

    @Slot()
    def browseFolder(self):
        self._choose(self._settings.set_folder)

    @Slot()
    def pasteSource(self):
        self._composer.setUrl(QApplication.clipboard().text())
        self._composer.pasted()

    def _enqueue(self, tasks):
        if self._closing or self._pending or self._dialog:
            return
        if len(tasks) == 1 and tasks[0].playlist:
            self._playlist = tasks[0]
            self.changed.emit()
            self.playlistRequested.emit()
            return
        self._pending = tasks
        duplicate = next((found for task in tasks if (found := self.scheduler.find_duplicate(task))), None)
        if duplicate:
            self._duplicate_id = duplicate.id
            self.changed.emit()
            self.duplicateRequested.emit()
        else:
            self.confirmDuplicate(True, False)

    @Slot("QVariantList")
    def acceptPlaylist(self, indices):
        if not self._playlist:
            return
        task, self._playlist = self._playlist, None
        preferences = self.scheduler.preferences_for(task)
        self._enqueue(self._composer.submissions.playlist(task, [int(i) for i in indices], preferences))

    @Slot(bool, bool)
    def confirmDuplicate(self, accepted, repeat):
        tasks, self._pending = self._pending, []
        if not accepted or not tasks:
            return
        for task in tasks:
            task.repeat = repeat
        # Both preferences and tasks were frozen at click time, before any dialog.
        prefs = self.scheduler.preferences_for(tasks[0])
        if prefs.ask_destination:
            self._choose(lambda folder: self._commit(tasks, folder), initial=prefs.folder)
        else:
            self._commit(tasks, prefs.folder)

    @Slot()
    def openDuplicate(self):
        if self.duplicateCanOpen:
            self.openResult(self._duplicate_id, False)
        self.confirmDuplicate(False, False)

    def _commit(self, tasks, folder):
        try:
            folder = str(validate_folder(folder))
            self._composer.submissions.commit(tasks, folder, repeat=any(task.repeat for task in tasks))
            self._settings.remember_folder(folder)
            self._feedback = ""
        except (OSError, ValueError):
            self._feedback = "error_folder_unavailable"
        self.changed.emit()

    @Slot(str)
    def cancelTask(self, ident):
        if ident in self.scheduler.tasks:
            self.scheduler.cancel(ident)

    @Slot(str)
    def retryTask(self, ident):
        if ident in self.scheduler.tasks:
            task = self.scheduler.tasks[ident]
            if task.playlist:
                self._playlist = task
                self.changed.emit()
                self.playlistRequested.emit()
            else:
                self.scheduler.retry(ident)

    @Slot(str)
    def removeTask(self, ident):
        if ident in self.scheduler.tasks and ident not in self.scheduler.jobs:
            self.scheduler.remove(ident)

    @Slot()
    def clearCompleted(self):
        for task in list(self.scheduler.tasks.values()):
            if task.state == State.COMPLETED and not task.hidden:
                self.removeTask(task.id)

    @Slot(str, bool)
    def openResult(self, ident, folder):
        from PySide6.QtCore import QProcess

        task = self.scheduler.tasks.get(ident)
        if not task or not task.final_path or not Path(task.final_path).is_file():
            self._feedback = "error_final_file_missing"
            self.changed.emit()
            return
        if folder:
            QProcess.startDetached("explorer.exe", ["/select,", str(Path(task.final_path))])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(task.final_path))

    @Slot()
    def openSupportedSites(self):
        QDesktopServices.openUrl(QUrl("https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md"))

    @Slot(str)
    def importTextFile(self, url):
        path = Path(QUrl(url).toLocalFile())
        try:
            if path.suffix.lower() == ".txt" and path.stat().st_size <= 1_000_000:
                self._composer.setUrl(path.read_text(encoding="utf-8-sig"))
                self.navigate("downloads")
        except (OSError, UnicodeError):
            self._feedback = "invalid_links"
            self.changed.emit()

    def _queue_finished(self, completed, failed):
        if self.tray and self.window and not self.window.isVisible():
            self.tray.showMessage(APP_NAME, f"{text(self.preferences.language, 'completed')}: {completed} · {text(self.preferences.language, 'failed')}: {failed}")

    @Slot()
    def restore(self):
        if self.window:
            if not self.window.isVisible() or self.window.windowState() == Qt.WindowState.WindowMinimized:
                self.window.showMaximized() if self._restore_maximized else self.window.showNormal()
            self.window.raise_()
            self.window.requestActivate()
            self._media.setActive(self._page == "downloads")

    @Slot()
    def quit(self):
        self._explicit_exit = True
        self.requestClose()

    @Slot(result=bool)
    def requestClose(self):
        if self._exit_ready:
            return True
        if self.preferences.close_to_tray and self.tray and not self._explicit_exit:
            if self.window:
                self._restore_maximized = self.window.windowState() == Qt.WindowState.WindowMaximized
                self.window.hide()
            self._media.setActive(False)
            return False
        if not self._closing:
            self._closing = True
            self.changed.emit()
            if self._dialog:
                self._dialog.reject()
            self._composer.shutdown()
            self._media.shutdown()
            self.scheduler.shutdown()
            self._shutdown_started = monotonic()
            self._shutdown_timer.start()
        self._finish_shutdown()
        return False

    def _finish_shutdown(self):
        if not self.scheduler.jobs and not self._composer.busy:
            self._shutdown_timer.stop()
            self._exit_ready = True
            if self.tray:
                self.tray.hide()
            self.exitReady.emit()
        elif monotonic() - self._shutdown_started > 5:
            # Keep the event loop alive until finished signals retire their jobs.
            self.scheduler.force_stop()
            self._composer.force_stop()

    def dispose(self):
        if self.tray:
            self.tray.hide()
        if self.menu:
            self.menu.deleteLater()
        self._media.shutdown()
