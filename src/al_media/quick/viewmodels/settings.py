from __future__ import annotations

from dataclasses import asdict, replace

from PySide6.QtCore import Property, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot

from al_media.config import Preferences, normalize_recent_folders
from al_media.core.folders import inspect_folder


class _FolderSignals(QObject):
    finished = Signal(object)


class _FolderWork(QRunnable):
    def __init__(self, revision, value, apply):
        super().__init__()
        self.revision, self.value, self.apply = revision, value, apply
        self.signals = _FolderSignals()

    def run(self):
        check = inspect_folder(self.value, create=self.apply)
        self.signals.finished.emit((self.revision, self.apply, check))


class SettingsViewModel(QObject):
    changed = Signal()
    preferences_changed = Signal()
    browse_requested = Signal()
    folderApplied = Signal()

    ENUMS = {"theme": {"system", "dark", "light"}, "language": {"ru", "en", "be", "uk"}, "name_style": {"title", "artist_title"}, "subfolders": {"none", "source", "author", "playlist"}}
    BOOLEANS = {"music_tags", "music_cover", "close_to_tray", "ask_destination"}

    def __init__(self, preferences: Preferences, parent=None, *, persist=True):
        super().__init__(parent)
        self.preferences, self.persist = preferences, persist
        self._number = str(preferences.concurrency)
        self._folder = preferences.folder
        self._folder_error = ""
        self._folder_state = "idle"
        self._folder_revision = 0
        self._folder_work = self._folder_pending = None
        self._closing = False
        self._folder_timer = QTimer(self, singleShot=True, interval=350)
        self._folder_timer.timeout.connect(self._check_folder)
        self._error = self._saved = ""
        self._clear_saved = QTimer(self, singleShot=True, interval=1800)
        self._clear_saved.timeout.connect(self._clear_status)

    @Property("QVariantMap", notify=changed)
    def state(self):
        valid_number = self._number.isascii() and self._number.isdigit() and 1 <= int(self._number) <= 5
        return {
            **asdict(self.preferences),
            "numberDraft": self._number,
            "numberInvalid": not valid_number,
            "folderDraft": self._folder,
            "folderError": self._folder_error,
            "folderStatus": self._folder_state,
            "folderMessage": self._folder_error or {"found": "folder_found", "missing": "folder_will_create", "checking": "folder_checking",
                                                    "applying": "folder_checking", "saved": "folder_saved", "created": "folder_created"}.get(self._folder_state, ""),
            "folderDirty": self._folder != self.preferences.folder,
            "error": self._error,
            "saved": self._saved,
            "recentFolders": normalize_recent_folders([self.preferences.folder, *self.preferences.recent_folders]),
            "recentAlternatives": normalize_recent_folders([self.preferences.folder, *self.preferences.recent_folders])[1:],
        }

    def _clear_status(self):
        self._saved = ""
        if self._folder_state in {"saved", "created"}:
            self._folder_state = "found"
        self.changed.emit()

    def commit(self, candidate: Preferences) -> bool:
        try:
            if self.persist:
                candidate.save()
        except OSError:
            self._error = "settings_error"
            self.changed.emit()
            return False
        for key, value in asdict(candidate).items():
            setattr(self.preferences, key, value)
        valid_number = self._number.isascii() and self._number.isdigit() and 1 <= int(self._number) <= 5
        self._error, self._saved = "" if valid_number else "concurrency_invalid", "saved"
        self.changed.emit()
        self.preferences_changed.emit()
        self._clear_saved.start()
        return True

    @Slot(str, "QVariant")
    def setValue(self, key, value):
        if key in self.ENUMS and value in self.ENUMS[key] or key in self.BOOLEANS and isinstance(value, bool):
            self.commit(replace(self.preferences, **{key: value}))

    @Slot(str)
    def setConcurrency(self, value):
        self._number = value
        if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 5:
            self._error = "concurrency_invalid"
            self.changed.emit()
            return
        self.commit(replace(self.preferences, concurrency=int(value)))

    @Slot(str)
    def chooseRecent(self, folder):
        if folder in normalize_recent_folders([self.preferences.folder, *self.preferences.recent_folders]):
            self.set_folder(folder)

    def set_folder(self, folder: str):
        self.editFolder(folder)
        self.applyFolder()

    @Slot(str)
    def editFolder(self, value):
        if self._closing:
            return
        self._folder_revision += 1
        self._folder, self._folder_error, self._saved = value, "", ""
        self._folder_state = "idle"
        self._folder_pending = None
        self._folder_timer.start()
        self.changed.emit()

    @Slot()
    def applyFolder(self):
        if self._closing:
            return
        self._folder_timer.stop()
        self._request_folder(True)

    @Slot()
    def checkFolder(self):
        if not self._closing:
            self._folder_timer.start()

    def _check_folder(self):
        self._request_folder(False)

    def _request_folder(self, apply):
        request = (self._folder_revision, self._folder, apply)
        if self._closing:
            return
        if self._folder_work:
            if (self._folder_work.revision, self._folder_work.value, self._folder_work.apply) != request:
                self._folder_pending = request
            return
        self._folder_error = ""
        self._folder_state = "applying" if apply else "checking"
        self.changed.emit()
        work = self._folder_work = _FolderWork(*request)
        work.signals.finished.connect(self._folder_checked, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(work)

    @Slot(object)
    def _folder_checked(self, result):
        revision, apply, check = result
        self._folder_work = None
        if revision == self._folder_revision:
            self._folder_error, self._folder_state = check.error, check.state
            if apply and not check.error:
                candidate = replace(self.preferences, folder=check.path,
                                    recent_folders=normalize_recent_folders([check.path, *self.preferences.recent_folders, self.preferences.folder]))
                if self.commit(candidate):
                    self._folder = check.path
                    self._folder_state = "created" if check.created else "saved"
                    self.changed.emit()
                    self.folderApplied.emit()
                else:
                    self._folder_error, self._folder_state = "settings_error", "error"
            self.changed.emit()
        pending, self._folder_pending = self._folder_pending, None
        if pending and pending[0] == self._folder_revision and not self._closing:
            self._request_folder(pending[2])

    @Slot()
    def resetFolder(self):
        self._folder_revision += 1
        self._folder_timer.stop()
        self._folder_pending = None
        self._folder, self._folder_error = self.preferences.folder, ""
        self._folder_state = "idle"
        self.changed.emit()

    @property
    def busy(self):
        return self._folder_work is not None

    def shutdown(self):
        self._closing = True
        self._folder_timer.stop()
        self._folder_pending = None

    @Slot()
    def browse(self):
        self.browse_requested.emit()

    def remember_folder(self, folder: str) -> None:
        recent = normalize_recent_folders([self.preferences.folder, folder, *self.preferences.recent_folders])
        if recent != self.preferences.recent_folders:
            self.commit(replace(self.preferences, recent_folders=recent))
