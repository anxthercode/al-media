import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, QProcessEnvironment, Qt, QUrl
from PySide6.QtGui import QDropEvent, QFont, QFontDatabase
from PySide6.QtWidgets import QComboBox, QLabel, QMessageBox, QPushButton, QSystemTrayIcon

from al_media.config import Preferences
from al_media.core.engine import EngineJob
from al_media.core.scheduler import Scheduler
from al_media.database import Database
from al_media.models import State, Task
from al_media.ui.main_window import MainWindow
from al_media.ui.selection import default_selection
from al_media.ui.task_options import PlaylistDialog, TaskOptionsDialog, parse_time


@pytest.fixture
def gui(qtbot, tmp_path, monkeypatch):
    for name in ("segoeui.ttf", "seguisb.ttf"):
        path = Path("C:/Windows/Fonts") / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    if "Segoe UI" in QFontDatabase.families():
        from PySide6.QtWidgets import QApplication
        QApplication.instance().setFont(QFont("Segoe UI", 10))
    monkeypatch.setattr(Preferences, "save", lambda self: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    db = Database(tmp_path / "gui.sqlite3")
    prefs = Preferences(folder=str(tmp_path))
    tools = {name: Path(sys.executable) for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno")}
    scheduler = Scheduler(db, tools, prefs)
    window = MainWindow(scheduler, prefs, probe_tools=False)
    qtbot.addWidget(window)
    window.show()
    yield window, scheduler, prefs
    window.explicit_exit = True
    window.close()
    db.close()


@pytest.fixture
def fake_engine(monkeypatch):
    original = EngineJob.start
    fixture = Path(__file__).parent / "fixtures/fake_engine.py"
    def start(job):
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        job.process.setProcessEnvironment(environment)
        job.process.setArguments([str(fixture), *job.process.arguments()])
        original(job)
    monkeypatch.setattr(EngineJob, "start", start)


def test_sidebar_languages_and_settings_autosave(gui):
    window, _, prefs = gui
    assert len(window.nav.buttons()) == 3
    assert [window.language.itemData(i) for i in range(window.language.count())] == ["en", "ru", "be", "uk"]
    assert not hasattr(window, "history_page")
    assert not hasattr(window, "save_button")
    window.language.setCurrentIndex(window.language.findData("be"))
    window.theme.setCurrentIndex(window.theme.findData("light"))
    assert prefs.language == "be" and prefs.theme == "light"
    assert window.nav_buttons[0].text() == "Спампоўкі"
    assert "#f6f8fa" in window.styleSheet()


def test_idle_close_has_no_dialog(gui, monkeypatch):
    window, _, _ = gui
    def unexpected(*_):
        raise AssertionError("Idle close should not ask a question")
    monkeypatch.setattr(QMessageBox, "question", unexpected)
    assert window.close()


def test_dropped_text_file_becomes_batch_without_starting_download(gui, tmp_path):
    window, scheduler, _ = gui
    text_file = tmp_path / "links.txt"
    text_file.write_text("https://example.test/one\nhttps://example.test/two", encoding="utf-8-sig")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(text_file))])
    event = QDropEvent(QPointF(300, 200), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(event)
    assert window.input.text().splitlines() == ["https://example.test/one", "https://example.test/two"]
    assert window.add_button.isEnabled() and not scheduler.tasks


def test_invalid_folder_preserves_preferences(gui, monkeypatch):
    from al_media import config
    window, _, prefs = gui
    before = prefs.folder
    monkeypatch.setattr(QMessageBox, "warning", lambda *_: None)
    def denied(_):
        raise OSError("Access denied")
    monkeypatch.setattr(config, "validate_folder", denied)
    window.path_edit.setText("unavailable")
    assert window._save_settings() is False
    assert prefs.folder == before


def test_dynamic_quality_and_mp3_default(gui, qtbot):
    window, scheduler, prefs = gui
    task = Task("https://example.test/video", state=State.READY, formats=[
        {"vcodec": "h264", "acodec": "aac", "height": height} for height in (4320, 2160, 1080, 480)])
    scheduler.tasks[task.id] = task
    window._task_changed(task)
    window.select_task(task.id)
    picker = window.format_picker
    assert [picker.quality.itemText(i) for i in range(picker.quality.count())] == ["4320p — максимум", "2160p", "1080p", "480p"]
    qtbot.wait(30)
    preview_height = window.media_preview.height()
    picker.audio.click()
    qtbot.wait(30)
    assert window.media_preview.height() == preview_height
    assert task.selection == "mp3:320"
    picker.bitrate.setCurrentIndex(picker.bitrate.findData("mp3:128"))
    assert prefs.mp3_bitrate == 128 and prefs.media_mode == "audio"
    assert default_selection(Task(task.url, formats=task.formats), prefs) == "mp3:128"
    picker.audio_format.setCurrentIndex(picker.audio_format.findData("audio"))
    assert task.selection == "audio"
    assert picker.bitrate_field.isHidden()


def test_analyze_before_download_and_no_draft_in_history(gui, fake_engine, qtbot):
    window, scheduler, _ = gui
    window.input.setText("https://fixture.test/video")
    assert not window.add_button.isEnabled()
    qtbot.waitUntil(lambda: window.preview_task is not None, timeout=10000)
    assert not scheduler.tasks
    assert window.source_title.text() == "Fixture"
    assert window.format_picker.quality.itemText(0) == "720p — максимум"
    window.format_picker.audio.click()
    window.add_button.click()
    qtbot.waitUntil(lambda: len(scheduler.tasks) == 1 and all(task.state == State.COMPLETED for task in scheduler.tasks.values()) and not scheduler.jobs, timeout=10000)
    task = next(iter(scheduler.tasks.values()))
    assert task.selection == "mp3:320"
    assert Path(task.final_path).is_file()
    assert window.input.text() == task.url
    assert window.preview_task is not task and window.preview_task.state == State.READY
    window.format_picker.video.click()
    window.add_button.click()
    qtbot.waitUntil(lambda: len(scheduler.tasks) == 2 and all(item.state == State.COMPLETED for item in scheduler.tasks.values()) and not scheduler.jobs, timeout=10000)
    assert task.selection == "mp3:320"
    assert len({item.id for item in scheduler.tasks.values()}) == 2
    assert window.input.text() == task.url and window.add_button.isEnabled()


def test_card_actions_follow_state(gui):
    window, scheduler, _ = gui
    task = Task("https://example.test/video", state=State.READY, formats=[{"vcodec": "h264", "height": 480}])
    scheduler.tasks[task.id] = task
    window._task_changed(task)
    card = window.cards[task.id]
    assert not card.start.isHidden() and card.cancel.isHidden() and card.bar.isHidden()
    task.state, task.error = State.FAILED, "error_network"
    card.render(task)
    assert "ETA" not in card.status.text()
    assert card.open_file.isHidden()
    task.state, task.processing_stage, task.percent = State.POSTPROCESSING, "merging", 100
    card.render(task)
    assert card.bar.minimum() == card.bar.maximum() == 0
    assert card.status.text().startswith("Объединение дорожек")


def test_clip_and_subtitles_are_applied_only_on_accept(gui):
    window, _, prefs = gui
    task = Task("https://example.test/video", duration=120, audio_languages=["en", "be"], subtitles={"en": [{"ext": "vtt"}]})
    dialog = TaskOptionsDialog(task, prefs, window)
    dialog.clip.setChecked(True)
    dialog.start.setText("00:10")
    dialog.end.setText("00:25.5")
    dialog.audio_track.setCurrentIndex(2)
    dialog.subtitles.setCurrentIndex(1)
    dialog.subtitle_mode.setCurrentIndex(1)
    dialog.accept()
    assert (task.clip_start, task.clip_end, task.audio_language, task.subtitle_language, task.subtitle_mode) == (10, 25.5, "be", "en", "embedded")
    invalid = TaskOptionsDialog(task, prefs, window)
    invalid.start.setText("00:59")
    invalid.end.setText("00:15")
    invalid.accept()
    assert invalid.result() == 0 and invalid.error.text()
    assert task.clip_start == 10
    assert parse_time("1:02:03.5") == 3723.5


def test_voice_change_updates_format_and_resume_name(gui):
    window, _, prefs = gui
    task = Task("https://example.test/video", selection="m4a", output_stem="old", audio_language="en", audio_track_ids=["original"],
                audio_tracks=[{"language": "en", "label": "Original", "ids": ["original"]},
                              {"language": "en", "label": "Voice over", "ids": ["dub"]}],
                formats=[{"format_id": "original", "ext": "m4a", "acodec": "aac", "vcodec": "none"},
                         {"format_id": "dub", "ext": "webm", "acodec": "opus", "vcodec": "none"}])
    dialog = TaskOptionsDialog(task, prefs, window)
    dialog.audio_track.setCurrentIndex(2)
    dialog.accept()
    assert task.audio_track_ids == ["dub"] and task.audio_language == "en"
    assert task.selection == "audio" and not task.output_stem


def test_playlist_selection_excludes_unavailable_entries(gui):
    window, _, _ = gui
    task = Task("https://example.test/playlist", playlist=True, playlist_entries=[
        {"index": 1, "title": "First", "url": "https://example.test/1"},
        {"index": 2, "title": "Unavailable", "url": ""},
        {"index": 3, "title": "Third", "url": "https://example.test/3"}])
    dialog = PlaylistDialog(task, "ru", window)
    assert [entry["index"] for entry in dialog.selected_entries()] == [1, 3]
    dialog._select(False)
    assert not dialog.add.isEnabled()
    dialog._select(True)
    assert len(dialog.selected_entries()) == 2


def test_tray_action_never_hides_without_available_tray(gui, monkeypatch):
    window, _, _ = gui
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    window._minimize_to_tray()
    assert window.isVisible()


def test_close_to_tray_and_explicit_exit(gui, monkeypatch):
    window, _, prefs = gui
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    prefs.close_to_tray = True
    window.close()
    assert not window.isVisible() and not window.closing
    window._show_window()
    window._exit_application()
    assert window.closing


def test_tray_restore_preserves_maximized_and_normal_window(gui, qtbot, monkeypatch):
    window, _, _ = gui
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    for maximized in (True, False):
        window.showMaximized() if maximized else window.showNormal()
        qtbot.wait(20)
        window._minimize_to_tray()
        window._show_window()
        assert window.isVisible() and window.isMaximized() == maximized


def test_common_grid_and_compact_preview_with_visible_download_action(gui, qtbot):
    window, _, _ = gui
    window.resize(1920, 1080)
    window.preview_task = Task("https://example.test/video", title="Video", duration=100, state=State.READY,
                               formats=[{"vcodec": "h264", "acodec": "aac", "height": 2160}])
    window._render_preview()
    qtbot.wait(50)
    assert window.download_page.width() == window.settings_page.maximumWidth() == window.about_page.maximumWidth()
    assert window.media_preview.width() >= 500
    assert window.media_preview.height() <= 260
    assert window.input.width() == window.source_layout.width()
    assert window.add_button.mapTo(window.download_page, window.add_button.rect().topLeft()).y() > window.source_layout.geometry().bottom()
    window.input.setFocus()
    qtbot.keyClick(window.input, Qt.Key.Key_Tab)
    assert window.format_picker.video.hasFocus()


def test_compact_list_selection_and_about_contents(gui, tmp_path):
    from al_media.ui.pages import SUPPORTED_SITES
    from al_media.ui.widgets import Foldout

    window, scheduler, _ = gui
    path = tmp_path / "Song.mp3"
    path.write_bytes(b"music")
    task = Task("https://example.test/song", title="Song", state=State.COMPLETED, final_path=str(path))
    scheduler.tasks[task.id] = task
    window._task_changed(task)
    window.select_task(task.id)
    assert window.source_title.text() == "Song" and not window.media_preview.isHidden()
    assert window.cards[task.id].bar.isHidden()
    assert not hasattr(window, "paste_button") and not hasattr(window, "tray_button")
    assert not window.settings_page.findChildren(Foldout) and not window.about_page.findChildren(Foldout)
    assert [name for name, _ in SUPPORTED_SITES] == ["YouTube", "Facebook", "Instagram", "TikTok", "SoundCloud", "X (Twitter)"]
    labels = [label.text() for label in window.about_page.findChildren(QLabel)]
    assert "Developed by Vladislav Galkin (anxthercode)" in labels
    assert window.version_label.text().startswith("Версия ")


def test_translated_buttons_fit_minimum_window(gui, qtbot):
    window, _, _ = gui
    window.resize(960, 700)
    qtbot.wait(20)
    assert window.input.height() == 38 and window.add_button.height() == 42
    assert window.add_button.isHidden() and window.format_picker.modes.isHidden()
    for language in ("en", "ru", "be", "uk"):
        window.language.setCurrentIndex(window.language.findData(language))
        for index in range(3):
            window._navigate(index)
            qtbot.wait(20)
            scroll = window.stack.currentWidget()
            assert scroll.horizontalScrollBar().maximum() == 0
            for button in window.findChildren(QPushButton):
                if button.isVisible() and button.text():
                    text_width = button.fontMetrics().horizontalAdvance(button.text())
                    icon_width = button.iconSize().width() + 4 if not button.icon().isNull() else 0
                    assert button.width() >= text_width + icon_width, (language, button.text(), button.width(), text_width)
            for combo in window.findChildren(QComboBox):
                if combo.isVisible() and combo.currentText():
                    assert combo.width() > combo.fontMetrics().horizontalAdvance(combo.currentText()) + 20
            assert not any(label.text() == "Изменения сохраняются автоматически" for label in window.findChildren(QLabel))


def test_progress_lane_and_completed_files_are_separate(gui, qtbot, tmp_path):
    window, scheduler, _ = gui
    window.resize(1280, 1000)
    task = Task("https://example.test/video", title="Track", selection="mp3:320", state=State.DOWNLOADING, percent=43, speed=1048576, eta=20)
    scheduler.tasks[task.id] = task
    window._task_changed(task)
    qtbot.wait(30)
    card = window.cards[task.id]
    assert window.active_layout.indexOf(card) == 0 and window.cards_layout.indexOf(card) == -1
    assert not card.bar.isHidden() and window.completed_panel.isHidden()
    left = card.bar.mapTo(window.download_page, card.bar.rect().topLeft())
    right = card.bar.mapTo(window.download_page, card.bar.rect().topRight())
    input_origin = window.input.mapTo(window.download_page, window.input.rect().topLeft())
    assert left.x() == input_origin.x()
    assert right.x() == input_origin.x() + window.input.width() - 1
    assert left.y() > window.add_button.mapTo(window.download_page, window.add_button.rect().bottomLeft()).y()
    path = tmp_path / "Actual track.mp3"
    path.write_bytes(b"audio")
    task.state, task.final_path, task.output_bitrate = State.COMPLETED, str(path), 192000
    window._task_changed(task)
    qtbot.wait(20)
    assert window.cards_layout.indexOf(card) == 0 and window.active_layout.indexOf(card) == -1
    assert card.bar.isHidden() and card.status.isHidden()
    assert card.title.text() == path.name and "192" in card.details.text()
    assert "Готово" not in card.details.text()
    assert card.open_file.text() == "Открыть файл" and card.open_folder.text() == "Показать в папке"


def test_popup_options_keep_composer_and_arrow_geometry(gui, qtbot):
    from PySide6.QtWidgets import QStyle, QStyleOptionComboBox

    window, _, _ = gui
    window.resize(1280, 1000)
    task = Task("https://example.test/video", title="A clear title", author="Author", duration=120, state=State.READY,
                formats=[{"format_id": "v", "height": 2160, "vcodec": "h264", "acodec": "aac"}],
                subtitles={"en": [{"ext": "vtt"}]})
    window.preview_task = task
    window._render_preview()
    qtbot.wait(30)
    def origin(widget):
        return widget.mapTo(window.download_page, widget.rect().topLeft())
    before = origin(window.add_button)
    for language in ("en", "ru", "be", "uk"):
        window.language.setCurrentIndex(window.language.findData(language))
        window.preview_advanced.setChecked(True)
        qtbot.wait(30)
        assert origin(window.add_button) == before
        editor = window.options_editor
        editor.clip.setChecked(True)
        editor.start.setText("0:10")
        editor.end.setText("0:25")
        editor.subtitles.setCurrentIndex(2)
        editor.apply_button.click()
        assert not window.options_popup.isVisible()
        assert (task.clip_start, task.clip_end, task.subtitle_mode) == (10, 25, "embedded")
        window.preview_advanced.setChecked(False)
        qtbot.wait(20)
        assert origin(window.add_button) == before
        for combo in (window.format_picker.quality, editor.audio_track, editor.subtitles):
            option = QStyleOptionComboBox()
            combo.initStyleOption(option)
            arrow = combo.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxArrow, combo)
            assert combo.width() - (arrow.center().x() + 7) >= 10


def test_batch_starts_downloads_and_keeps_selection_snapshot(gui, fake_engine, qtbot):
    window, scheduler, prefs = gui
    prefs.media_mode, prefs.audio_format, prefs.mp3_bitrate = "audio", "mp3", 320
    window.input.setText("https://fixture.test/one\nhttps://fixture.test/two\nhttps://fixture.test/three")
    window._add_urls()
    assert len(scheduler.tasks) == 3
    assert all(task.auto_start and task.selection == "mp3:320" for task in scheduler.tasks.values())
    prefs.media_mode, prefs.mp3_bitrate = "video", 128
    qtbot.waitUntil(lambda: not scheduler.jobs and all(task.state in {State.COMPLETED, State.FAILED} for task in scheduler.tasks.values()), timeout=15000)
    assert all(task.state == State.COMPLETED for task in scheduler.tasks.values()), [(task.state, task.error) for task in scheduler.tasks.values()]
    assert window.active_panel.isHidden()
    assert window.cards_layout.count() == 3
    assert all(task.selection == "mp3:320" for task in scheduler.tasks.values())


def test_invalid_inline_clip_blocks_download_without_moving_button(gui, qtbot):
    window, scheduler, _ = gui
    window.input.setText("https://example.test/video")
    window.preview_timer.stop()
    window.preview_task = Task(window.input.text(), title="Video", state=State.READY, duration=120,
                               formats=[{"vcodec": "h264", "acodec": "aac", "height": 720}])
    window._render_preview()
    qtbot.wait(30)
    before = window.add_button.mapTo(window.download_page, window.add_button.rect().topLeft())
    editor = window.options_editor
    editor.clip.setChecked(True)
    editor.start.setText("0:50")
    editor.end.setText("0:10")
    window._add_urls()
    qtbot.wait(20)
    assert not scheduler.tasks
    assert window.preview_advanced.isChecked() and editor.error.text()
    assert editor.error.geometry().bottom() < editor.height()
    assert before == window.add_button.mapTo(window.download_page, window.add_button.rect().topLeft())


def test_empty_loading_failure_and_clear_hide_download_controls(gui, fake_engine, qtbot):
    window, _, _ = gui
    assert window.empty_hint.isVisible()
    assert not window.source_layout.isVisible()
    assert not window.add_button.isVisible() and not window.format_picker.modes.isVisible()
    window.input.setText("https://fixture.test/video")
    assert window.loading_panel.isVisible() and window.analysis_status.isVisible()
    assert not window.parameter_fields.isVisible() and not window.add_button.isVisible()
    qtbot.waitUntil(lambda: window.preview_task is not None, timeout=10000)
    assert window.source_layout.isVisible() and window.add_button.isVisible()
    assert not window.loading_panel.isVisible()
    window._input_failure("error_network")
    assert window.input_error.isVisible() and not window.add_button.isVisible()
    window.input.clear()
    assert window.empty_hint.isVisible() and not window.loading_panel.isVisible()
    assert not window.add_button.isVisible() and not window.format_picker.modes.isVisible()


def test_audio_popup_only_clip_and_escape_does_not_apply(gui, qtbot):
    window, _, _ = gui
    task = Task("https://example.test/video", title="Video", duration=180, state=State.READY,
                formats=[{"height": 1080, "vcodec": "h264", "acodec": "aac"}], subtitles={"en": [{"ext": "vtt"}]})
    window.preview_task = task
    window._render_preview()
    window.format_picker.audio.click()
    window.preview_advanced.click()
    qtbot.wait(20)
    editor = window.options_editor
    assert window.options_popup.isVisible()
    assert editor.audio_track.isHidden() and editor.subtitles.isHidden()
    editor.clip.setChecked(True)
    editor.start.setText("0:30")
    editor.end.setText("2:00")
    assert task.clip_start is None
    editor.apply_button.click()
    assert (task.clip_start, task.clip_end) == (30, 120)
    assert "00:30–02:00" in window.preview_advanced.text()
    window.preview_advanced.click()
    editor.start.setText("0:45")
    qtbot.keyClick(editor.start, Qt.Key.Key_Escape)
    assert not window.options_popup.isVisible() and not window.preview_advanced.isChecked()
    assert task.clip_start == 30 and editor.start.text() == "00:30"


def test_download_action_fits_desktop_sizes_and_switch_settles(gui, qtbot):
    window, _, _ = gui
    task = Task("https://example.test/video", title="Video", author="Author", duration=120, state=State.READY,
                formats=[{"height": 2160, "vcodec": "h264", "acodec": "aac"}])
    window.preview_task = task
    window._render_preview()
    for width, height in ((960, 640), (1280, 720), (1536, 864), (1920, 1080)):
        window.resize(width, height)
        qtbot.wait(30)
        scroll = window.stack.currentWidget()
        assert scroll.verticalScrollBar().maximum() == 0, (width, height)
        for _ in range(3):
            window.format_picker.audio.click()
            qtbot.wait(15)
            window.format_picker.video.click()
        qtbot.wait(230)
        switch = window.format_picker.modes
        assert switch.highlight.geometry() == window.format_picker.video.geometry()
        assert window.add_button.isVisible()


def test_select_completed_file_keeps_url_and_creates_editable_draft(gui):
    window, scheduler, _ = gui
    task = Task("https://example.test/video", title="Video", state=State.COMPLETED, final_path="D:/old.mkv",
                formats=[{"height": 720, "vcodec": "h264", "acodec": "aac"}])
    scheduler.tasks[task.id] = task
    window.select_task(task.id)
    assert window.input.text() == task.url
    assert window.preview_task.id != task.id and window.preview_task.state == State.READY
    assert window.add_button.isEnabled() and window.format_picker.isEnabled()
    window.format_picker.audio.click()
    assert task.selection == "best" and task.final_path == "D:/old.mkv"


def test_combo_popup_keeps_options_open_until_apply(gui, qtbot):
    window, _, _ = gui
    task = Task("https://example.test/video", duration=180, state=State.READY,
                formats=[{"height": 1080, "vcodec": "h264", "acodec": "aac"}], subtitles={"en": [{"ext": "vtt"}]})
    window.preview_task = task
    window._render_preview()
    window.preview_advanced.click()
    combo = window.options_editor.subtitles
    qtbot.mouseClick(combo, Qt.MouseButton.LeftButton)
    qtbot.wait(20)
    assert window.options_popup.isVisible() and combo.view().isVisible()
    qtbot.keyClick(combo.view(), Qt.Key.Key_Down)
    qtbot.keyClick(combo.view(), Qt.Key.Key_Enter)
    assert window.options_popup.isVisible() and combo.currentIndex() == 1
    assert task.subtitle_mode == "none"
    window.options_editor.apply_button.click()
    assert task.subtitle_language == "en" and task.subtitle_mode == "sidecar"


def test_settings_path_and_about_footer_alignment(gui, qtbot):
    window, _, _ = gui
    window.resize(1536, 864)
    window._navigate(1)
    qtbot.wait(30)
    assert window.path_edit.width() == 440
    assert window.choose_button.x() - window.path_edit.geometry().right() <= 16
    window._navigate(2)
    qtbot.wait(30)
    assert window.about_author.y() > window.about_page.height() - 110


def test_download_spacing_and_late_source_facts_preserve_open_options(gui, qtbot):
    window, _, _ = gui
    task = Task("https://example.test/reel", title="Reel", state=State.READY,
                formats=[{"height": 1920, "vcodec": "h264", "acodec": "aac", "tbr": 1500}])
    window.preview_task = task
    window._render_preview()
    qtbot.wait(30)
    button_top = window.add_button.mapTo(window.download_page, window.add_button.rect().topLeft()).y()
    fields_bottom = window.parameter_fields.mapTo(window.download_page, window.parameter_fields.rect().bottomLeft()).y()
    assert 20 <= button_top - fields_bottom <= 24
    window.preview_advanced.click()
    window.options_editor.clip.setChecked(True)
    window.options_editor.start.setText("0:03")
    task.duration = 31.09
    window._source_probe_ready(task)
    assert window.source_duration.text() == "0:31" and "МБ" in window.source_size.text()
    assert window.options_editor.start.text() == "0:03" and window.options_popup.isVisible()
