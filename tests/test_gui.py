from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from al_media.config import Preferences
from al_media.core.scheduler import Scheduler
from al_media.database import Database
from al_media.models import State, Task
from al_media.ui.main_window import MainWindow


def test_gui_opens_offscreen(qtbot, tmp_path, monkeypatch):
    db = Database(tmp_path / "gui.sqlite3")
    prefs = Preferences(folder=str(tmp_path))
    scheduler = Scheduler(db, {name: Path("missing") for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno")}, prefs)
    window = MainWindow(scheduler, prefs)
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle() == "AL Media"
    assert window.nav.count() == 4
    monkeypatch.setattr(Preferences, "save", lambda self: None)
    window.language.setCurrentIndex(window.language.findData("uk"))
    window.theme.setCurrentIndex(window.theme.findData("light"))
    window._save_settings()
    assert window.nav.item(0).text() == "Завантаження"
    assert prefs.theme == "light"
    window.close()
    db.close()


def test_close_is_immediate_without_update_dialog(qtbot, tmp_path, monkeypatch):
    db = Database(tmp_path / "close.sqlite3")
    prefs = Preferences(folder=str(tmp_path))
    scheduler = Scheduler(db, {}, prefs)
    def unexpected_dialog(*args):
        raise AssertionError("Closing an idle app must never show an update dialog")
    monkeypatch.setattr(QMessageBox, "information", unexpected_dialog)
    window = MainWindow(scheduler, prefs)
    qtbot.addWidget(window)
    window.show()
    assert window.close()
    assert not window.isVisible()
    db.close()


def test_invalid_folder_does_not_change_preferences(qtbot, tmp_path, monkeypatch):
    from al_media import config
    db = Database(tmp_path / "settings.sqlite3")
    prefs = Preferences(folder=str(tmp_path))
    window = MainWindow(Scheduler(db, {}, prefs), prefs)
    qtbot.addWidget(window)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_: None)
    def denied(_path):
        raise OSError("Access denied")
    monkeypatch.setattr(config, "validate_folder", denied)
    window.path_edit.setText("unavailable")
    assert window._save_settings() is False
    assert prefs.folder == str(tmp_path)
    window.close()
    db.close()


def test_card_states_hide_irrelevant_actions(qtbot, tmp_path):
    db = Database(tmp_path / "cards.sqlite3")
    prefs = Preferences(folder=str(tmp_path))
    scheduler = Scheduler(db, {}, prefs)
    task = Task("https://example.test/video", state=State.READY, formats=[{"vcodec": "h264", "height": 720}])
    scheduler.tasks[task.id] = task
    window = MainWindow(scheduler, prefs)
    qtbot.addWidget(window)
    card = window.cards[task.id]
    assert not card.start.isHidden()
    assert card.cancel.isHidden()
    assert card.open_file.isHidden()
    assert card.bar.isHidden()
    task.state = State.FAILED
    task.error = "error_network"
    card.render(task)
    assert card.bar.isHidden()
    assert "ETA" not in card.status.text()
    window.close()
    db.close()



def test_source_quality_and_separate_audio_choices(qtbot, tmp_path):
    db = Database(tmp_path / "quality.sqlite3")
    prefs = Preferences(folder=str(tmp_path))
    scheduler = Scheduler(db, {}, prefs)
    task = Task("https://example.test/video", state=State.READY, formats=[
        {"vcodec": "h264", "acodec": "aac", "height": h} for h in (1080, 720, 480)
    ])
    scheduler.tasks[task.id] = task
    window = MainWindow(scheduler, prefs)
    qtbot.addWidget(window)
    card = window.cards[task.id]
    assert [card.selection.itemText(i) for i in range(card.selection.count())] == [
        "1080p — лучшее качество", "720p — меньше размер", "480p — меньше размер"]
    card.selection.setCurrentIndex(card.selection.findData("video:720"))
    assert task.selection == "video:720"
    card.media_kind.setCurrentIndex(card.media_kind.findData("mp3"))
    assert task.selection == "mp3:192"
    assert [card.selection.itemData(i) for i in range(card.selection.count())] == ["mp3:128", "mp3:192", "mp3:320"]
    card.selection.setCurrentIndex(card.selection.findData("mp3:320"))
    assert task.selection == "mp3:320"
    card.media_kind.setCurrentIndex(card.media_kind.findData("video"))
    assert task.selection == "best"
    window.close()
    db.close()


def test_download_is_direct_and_quality_is_optional(qtbot, tmp_path, monkeypatch):
    db = Database(tmp_path / "simple-flow.sqlite3")
    prefs = Preferences(folder=str(tmp_path))
    scheduler = Scheduler(db, {}, prefs)
    window = MainWindow(scheduler, prefs)
    qtbot.addWidget(window)
    calls = []
    monkeypatch.setattr(scheduler, "add", lambda url, *, download=False: calls.append((url, download)))
    window.input.setPlainText("https://example.test/video")
    window.add_button.click()
    assert calls == [("https://example.test/video", True)]
    window.input.setPlainText("https://example.test/other")
    window.quality_button.click()
    assert calls[-1] == ("https://example.test/other", False)
    assert not hasattr(window, "cookie_mode")
    window.close()
    db.close()
