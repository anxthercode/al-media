from __future__ import annotations

from dataclasses import asdict, replace

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from al_media.config import Preferences, normalize_recent_folders, validate_folder


class SettingsViewModel(QObject):
    changed = Signal()
    preferences_changed = Signal()
    browse_requested = Signal()

    ENUMS = {"theme": {"system", "dark", "light"}, "language": {"ru", "en", "be", "uk"}, "name_style": {"title", "artist_title"}, "subfolders": {"none", "source", "author", "playlist"}}
    BOOLEANS = {"music_tags", "music_cover", "close_to_tray", "ask_destination"}

    def __init__(self, preferences: Preferences, parent=None, *, persist=True):
        super().__init__(parent)
        self.preferences, self.persist = preferences, persist
        self._number = str(preferences.concurrency)
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
            "error": self._error,
            "saved": self._saved,
            "recentAlternatives": normalize_recent_folders([self.preferences.folder, *self.preferences.recent_folders])[1:],
        }

    def _clear_status(self):
        self._saved = ""
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
        if folder in self.preferences.recent_folders:
            self.set_folder(folder)

    def set_folder(self, folder: str) -> bool:
        try:
            value = str(validate_folder(folder))
        except OSError:
            self._error = "error_folder_unavailable"
            self.changed.emit()
            return False
        return self.commit(replace(self.preferences, folder=value, recent_folders=normalize_recent_folders([value, *self.preferences.recent_folders, self.preferences.folder])))

    @Slot()
    def browse(self):
        self.browse_requested.emit()

    def remember_folder(self, folder: str) -> None:
        recent = normalize_recent_folders([self.preferences.folder, folder, *self.preferences.recent_folders])
        if recent != self.preferences.recent_folders:
            self.commit(replace(self.preferences, recent_folders=recent))
