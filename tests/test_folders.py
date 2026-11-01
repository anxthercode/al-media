from pathlib import Path
from time import monotonic, sleep

import pytest
from PySide6.QtCore import QTimer

import al_media.core.folders as folders
import al_media.quick.viewmodels.settings as settings_module
from al_media.config import Preferences
from al_media.core.folders import folder_path, inspect_folder
from al_media.quick.viewmodels.settings import SettingsViewModel


def test_folder_preview_is_read_only_and_apply_creates_nested_path(tmp_path):
    destination = tmp_path / "Новая папка" / "Музыка"
    preview = inspect_folder(str(destination))
    assert preview.state == "missing" and not preview.error and not destination.exists()
    applied = inspect_folder(str(destination), create=True)
    assert applied.state == "found" and applied.created and destination.is_dir()
    assert not list(destination.iterdir())  # The write probe cleans up its file.
    existing = inspect_folder(str(destination), create=True)
    assert not existing.created and not existing.error


@pytest.mark.parametrize("value", ["", "Music", "C:Music", 'C:\\Bad<name', 'C:\\Music\\NUL', 'C:\\Music\\COM1.txt', '"C:\\Music. "', 'C:\\Music\\bad|name'])
def test_invalid_windows_paths_are_rejected_before_any_creation(value):
    with pytest.raises(ValueError):
        folder_path(value)


def test_quoted_and_environment_paths_are_normalized(tmp_path, monkeypatch):
    monkeypatch.setenv("ALMEDIA_TEST_FOLDER", str(tmp_path))
    assert folder_path('"%ALMEDIA_TEST_FOLDER%\\Music"') == tmp_path / "Music"


def test_existing_file_and_write_permissions_have_distinct_feedback(tmp_path, monkeypatch):
    file = tmp_path / "file.txt"
    file.write_text("keep", encoding="utf-8")
    assert inspect_folder(str(file)).error == "folder_not_directory"
    assert inspect_folder(str(file / "nested")).error == "folder_not_directory"
    monkeypatch.setattr(folders.os, "access", lambda *_: False)
    assert inspect_folder(str(tmp_path)).error == "folder_denied"
    assert file.read_text(encoding="utf-8") == "keep"


def test_apply_checks_real_write_even_when_os_access_reports_success(tmp_path, monkeypatch):
    def denied(**_kwargs):
        raise PermissionError("Denied by ACL")

    monkeypatch.setattr(folders.os, "access", lambda *_: True)
    monkeypatch.setattr(folders.tempfile, "TemporaryFile", denied)
    assert inspect_folder(str(tmp_path)).state == "found"
    assert inspect_folder(str(tmp_path), create=True).error == "folder_denied"


def test_background_preview_does_not_create_and_escape_retires_stale_result(qtbot, tmp_path, monkeypatch):
    destination = tmp_path / "Draft"
    settings = SettingsViewModel(Preferences(folder=str(tmp_path)), persist=False)
    original = settings_module.inspect_folder

    def slow(value, **kwargs):
        sleep(0.12)
        return original(value, **kwargs)

    monkeypatch.setattr(settings_module, "inspect_folder", slow)
    ticks = []
    heartbeat = QTimer(interval=10)
    heartbeat.timeout.connect(lambda: ticks.append(monotonic()))
    heartbeat.start()
    settings.editFolder(str(destination))
    qtbot.waitUntil(lambda: settings.state["folderStatus"] == "missing", timeout=2000)
    assert not destination.exists() and len(ticks) >= 10
    settings.applyFolder()
    settings.resetFolder()
    qtbot.waitUntil(lambda: not settings.busy)
    heartbeat.stop()
    assert settings.preferences.folder == str(tmp_path) and settings.state["folderStatus"] == "idle"
    assert settings.state["folderDraft"] == str(tmp_path)


def test_latest_folder_apply_wins_without_overwriting_other_preferences(qtbot, tmp_path, monkeypatch):
    settings = SettingsViewModel(Preferences(folder=str(tmp_path)), persist=False)
    original = settings_module.inspect_folder

    def slow(value, **kwargs):
        sleep(0.1)
        return original(value, **kwargs)

    monkeypatch.setattr(settings_module, "inspect_folder", slow)
    settings.editFolder(str(tmp_path / "Old"))
    settings.applyFolder()
    settings.editFolder(str(tmp_path / "Latest"))
    settings.applyFolder()
    settings.setValue("theme", "light")
    qtbot.waitUntil(lambda: not settings.busy, timeout=2000)
    assert Path(settings.preferences.folder) == tmp_path / "Latest"
    assert settings.preferences.theme == "light"
    assert str(tmp_path / "Old") not in settings.preferences.recent_folders


def test_failed_settings_save_keeps_previous_folder(qtbot, tmp_path, monkeypatch):
    settings = SettingsViewModel(Preferences(folder=str(tmp_path)))

    def fail(_self):
        raise OSError("Settings unavailable")

    monkeypatch.setattr(Preferences, "save", fail)
    settings.editFolder(str(tmp_path / "Candidate"))
    settings.applyFolder()
    qtbot.waitUntil(lambda: not settings.busy)
    assert settings.preferences.folder == str(tmp_path)
    assert settings.state["folderError"] == "settings_error"
