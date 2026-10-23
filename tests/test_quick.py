"""Behavioral contracts for the native Qt Quick presentation and its boundaries."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from PySide6.QtCore import Q_ARG, QMetaObject, QModelIndex, QObject, QPointF, QSize, Qt, Signal
from PySide6.QtQml import QQmlProperty
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QSignalSpy, QTest

from al_media.application.submission import SubmissionService
from al_media.config import Preferences, normalize_recent_folders
from al_media.core.scheduler import Scheduler
from al_media.database import Database
from al_media.models import State, Task
from al_media.quick.bootstrap import QuickApplication
from al_media.quick.downloads_model import DownloadsModel
from al_media.quick.media import IconProvider, PreviewProvider
from al_media.quick.viewmodels.composer import ComposerViewModel
from al_media.quick.viewmodels.settings import SettingsViewModel

INFO = {
    "title": "Fixture title",
    "extractor_key": "YouTube",
    "uploader": "Author",
    "duration": 120,
    "formats": [
        {"format_id": "v1", "vcodec": "avc1", "acodec": "none", "height": 1080, "ext": "mp4", "filesize": 1_000_000},
        {"format_id": "v2", "vcodec": "avc1", "acodec": "none", "height": 720, "ext": "mp4", "filesize": 500_000},
        {"format_id": "a1", "vcodec": "none", "acodec": "aac", "ext": "m4a", "filesize": 200_000},
    ],
}


@pytest.fixture
def scheduler(qapp, tmp_path):
    db = Database(tmp_path / "quick.sqlite3")
    scheduler = Scheduler(db, {}, Preferences(folder=str(tmp_path / "downloads")))
    yield scheduler
    scheduler.shutdown()
    db.close()


def prepared(composer, url="https://example.test/video"):
    composer._url = url
    composer._ready(composer._generation, Task(url), deepcopy(INFO))
    return composer.task


def test_raw_range_survives_close_and_requires_explicit_application(scheduler):
    composer = ComposerViewModel(scheduler, scheduler.preferences, persist=False)
    prepared(composer)
    composer.toggleRange()
    composer.editRange("clip", True)
    composer.editRange("start", "1:")
    composer.closeRange()
    assert composer.state["rangeStart"] == "1:"
    assert not composer.state["canDownload"]
    assert not composer.applyRange()
    assert composer.task.clip_start is None
    composer.editRange("start", "0:10")
    composer.editRange("end", "0:23")
    assert composer.applyRange()
    assert composer.task.clip_start == 10 and composer.task.clip_end == 23
    assert composer.state["canDownload"]
    composer.setMode("audio")
    composer.select("mp3:320")
    assert composer.state["estimated"] == "520.0 КБ"
    composer.select("mp3:192")
    assert composer.state["estimated"] == "312.0 КБ"


def test_source_drafts_are_independent_and_bounded(scheduler):
    composer = ComposerViewModel(scheduler, scheduler.preferences, persist=False)
    prepared(composer, "https://example.test/a")
    composer.editRange("clip", True)
    composer.editRange("start", "1:")
    composer.setUrl("https://example.test/b")
    composer.timer.stop()
    prepared(composer, "https://example.test/b")
    assert composer.state["rangeStart"] == ""
    composer.setUrl("https://example.test/a")
    composer.timer.stop()
    prepared(composer, "https://example.test/a")
    assert composer.state["rangeStart"] == "1:"
    assert not composer.state["canDownload"]


def test_stale_metadata_and_failed_requests_do_not_replace_current_source(scheduler):
    class Job(QObject):
        metadata_ready = Signal(str, dict)
        failed = Signal(str, str)
        finished = Signal(str)

        def __init__(self, task, tools, preferences, mode, parent):
            super().__init__(parent)
            self.task = task
            self.cancelled = False

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

    composer = ComposerViewModel(scheduler, scheduler.preferences, persist=False, job_factory=Job)
    jobs = []
    for suffix in "abc":
        composer.setUrl("https://example.test/" + suffix)
        composer.analyze()
        jobs.append(composer._job)
    jobs[0].metadata_ready.emit(jobs[0].task.id, {**INFO, "title": "A"})
    jobs[1].failed.emit(jobs[1].task.id, "error_network")
    assert composer.task is None and composer.state["phase"] == "loading"
    jobs[2].metadata_ready.emit(jobs[2].task.id, {**INFO, "title": "C"})
    assert composer.task.title == "C"
    assert jobs[0].cancelled and jobs[1].cancelled
    assert not scheduler.tasks  # Preview extraction never becomes a queue item.
    composer.shutdown()


def test_submission_is_detached_and_preferences_are_frozen(scheduler, monkeypatch):
    composer = ComposerViewModel(scheduler, scheduler.preferences, persist=False)
    source = prepared(composer)
    service = SubmissionService(scheduler)
    scheduler.preferences.name_style = "artist_title"
    task = service.prepare(source, scheduler.preferences)
    folder = str(Path(scheduler.preferences.folder).parent / "one-off")
    monkeypatch.setattr(scheduler, "pump", lambda: None)
    service.commit([task], folder)
    saved = next(iter(scheduler.tasks.values()))
    assert saved is not source and saved.id != source.id
    assert saved.folder == folder and saved.state == State.QUEUED
    scheduler.preferences.music_tags = False
    scheduler.preferences.name_style = "title"
    composer.select("mp3:128")
    assert saved.selection == "best"
    assert saved.output_stem.startswith("Author — Fixture title")
    assert scheduler.preferences_for(saved).music_tags
    assert scheduler.preferences.folder != folder
    reloaded = scheduler.database.all()[0]
    assert reloaded.preferences_snapshot["name_style"] == "artist_title"


def test_settings_validate_without_overwriting_last_valid_value(scheduler):
    settings = SettingsViewModel(scheduler.preferences, persist=False)
    settings.setConcurrency("6")
    assert scheduler.preferences.concurrency == 3 and settings.state["numberDraft"] == "6"
    assert settings.state["error"] == "concurrency_invalid"
    settings.setConcurrency("4")
    assert scheduler.preferences.concurrency == 4 and not settings.state["error"]
    settings.setValue("language", "invalid")
    assert scheduler.preferences.language == "ru"
    settings.setValue("theme", "light")
    assert scheduler.preferences.theme == "light"


def test_settings_save_failure_preserves_preferences(scheduler, monkeypatch):
    settings = SettingsViewModel(scheduler.preferences)

    def fail(_self):
        raise OSError("fixture")

    monkeypatch.setattr(Preferences, "save", fail)
    settings.setValue("theme", "light")
    assert scheduler.preferences.theme == "dark" and settings.state["error"] == "settings_error"


def test_recent_folders_use_windows_identity_and_limit():
    result = normalize_recent_folders(["D:\\Media\\", "d:\\media", "D:\\One", "D:\\Two", "D:\\Three", "D:\\Four"])
    assert result == ["D:\\Media\\", "D:\\One", "D:\\Two", "D:\\Three"]


def test_model_changes_only_affected_roles_and_never_resets_on_progress(scheduler):
    model = DownloadsModel(scheduler, scheduler.preferences)
    task = Task("https://example.test/a", state=State.DOWNLOADING, title="Title", percent=10)
    scheduler.tasks[task.id] = task
    scheduler.changed.emit(task)
    resets = QSignalSpy(model.modelReset)
    changes = QSignalSpy(model.dataChanged)
    task.percent = 25
    scheduler.changed.emit(task)
    assert resets.count() == 0 and changes.count() == 1 and model.count == 1
    roles = changes.at(0)[2]
    assert [model.roleNames()[role].decode() for role in roles] == ["progress"]
    assert model.data(model.index(0), next(role for role, name in model.roleNames().items() if name == b"title")) == "Title"
    assert model.rowCount(QModelIndex()) == 1


@pytest.fixture
def quick(qapp, scheduler, qtbot):
    app = QuickApplication(qapp, scheduler, scheduler.preferences, isolated=True)
    app.window.resize(1280, 720)
    app.window.show()
    qtbot.wait(80)
    yield app
    app.controller.quit()
    qtbot.waitUntil(lambda: app.controller._exit_ready, timeout=5000)
    app.window.hide()
    app.dispose()
    qtbot.wait(20)


def item(quick, name):
    obj = quick.window.findChild(QQuickItem, name)
    if obj is None:
        # Repeater delegates can be visually parented outside QObject ownership.
        pending = [quick.window.contentItem()]
        while pending:
            candidate = pending.pop()
            if candidate.objectName() == name:
                obj = candidate
                break
            pending.extend(candidate.childItems())
    assert obj is not None, name
    return obj


def click(quick, name):
    obj = item(quick, name)
    p = obj.mapToScene(QPointF(obj.width() / 2, obj.height() / 2)).toPoint()
    QTest.mouseClick(quick.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)


def test_native_three_routes_range_toggle_and_navigation_preserve_draft(quick, qtbot):
    composer = quick.controller.composer
    prepared(composer)
    qtbot.wait(50)
    click(quick, "cropButton")
    assert composer.state["rangeOpen"]
    click(quick, "cropButton")
    assert not composer.state["rangeOpen"]
    composer.editRange("clip", True)
    composer.editRange("start", "1:")
    click(quick, "navSettings")
    assert quick.controller.page == "settings"
    quick.controller.back()
    assert composer.state["rangeStart"] == "1:" and not composer.state["canDownload"]
    click(quick, "navAbout")
    assert quick.controller.page == "about"
    assert not quick.warnings


@pytest.mark.parametrize("size", [(1280, 720), (1280, 800), (1536, 864), (1920, 1080), (1024, 700)])
def test_native_geometry_and_compact_navigation(quick, qtbot, size):
    quick.window.resize(*size)
    prepared(quick.controller.composer)
    qtbot.wait(60)
    for name in ("mediaPreview", "downloadButton", "configuration"):
        obj = item(quick, name)
        origin = obj.mapToScene(QPointF())
        assert origin.x() >= 0 and origin.x() + obj.width() <= size[0]
    assert item(quick, "downloadButton").width() == item(quick, "configuration").width()
    y = item(quick, "downloadButton").mapToScene(QPointF()).y()
    quick.controller.composer.toggleRange()
    assert item(quick, "downloadButton").mapToScene(QPointF()).y() == y
    quick.controller.navigate("settings")
    qtbot.wait(20)
    assert item(quick, "concurrencyField").width() == 112
    assert item(quick, "concurrencyField").property("leftPadding") == item(quick, "downloadFolder").property("leftPadding") == 14
    click(quick, "navAbout")
    assert quick.controller.page == "about"
    assert not quick.warnings


def test_native_popup_and_licenses_have_working_keyboard_close(quick, qtbot):
    prepared(quick.controller.composer)
    qtbot.wait(50)
    picker = item(quick, "qualityPicker")
    QMetaObject.invokeMethod(picker, "openMenu")
    qtbot.wait(50)
    assert picker.property("menuVisible")
    assert picker.property("menuHeight") >= 96
    popup = QQmlProperty.read(picker, "popup")
    content = popup.property("contentItem")
    origin = content.mapToScene(QPointF())
    assert origin.x() >= 0 and origin.y() >= 0
    assert origin.x() + content.width() <= quick.window.width()
    assert origin.y() + content.height() <= quick.window.height()
    # Click the actual second row, rather than merely checking an open flag.
    QTest.mouseClick(quick.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, (origin + QPointF(24, 72)).toPoint())
    assert quick.controller.composer.task.selection == "video:720"
    QMetaObject.invokeMethod(picker, "openMenu")
    QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    qtbot.wait(30)
    assert not picker.property("menuVisible")
    quick.controller.navigate("about")
    click(quick, "licensesButton")
    qtbot.wait(30)
    QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    qtbot.wait(30)
    assert item(quick, "licensesButton").hasActiveFocus()
    assert not quick.warnings


def test_changing_preferences_does_not_reset_focused_range(quick, qtbot):
    composer = quick.controller.composer
    prepared(composer)
    composer.toggleRange()
    qtbot.wait(30)
    field = item(quick, "rangeStart")
    quick.window.requestActivate()
    qtbot.wait(30)
    field.forceActiveFocus()
    assert field.hasActiveFocus()
    composer.editRange("clip", True)
    composer.editRange("start", "1:")
    quick.controller.settings.setValue("language", "en")
    assert field.hasActiveFocus(), "language"
    quick.controller.settings.setValue("theme", "light")
    assert field.hasActiveFocus(), "theme"
    task = Task("https://example.test/b", title="Other", state=State.DOWNLOADING, percent=4)
    quick.controller.scheduler.tasks[task.id] = task
    quick.controller.scheduler.changed.emit(task)
    assert field.hasActiveFocus(), "queue insertion"
    qtbot.wait(30)
    assert field.hasActiveFocus() and field.property("text") == "1:", (
        quick.window.isActive(),
        composer.state["rangeOpen"],
        field.isVisible(),
        item(quick, "rangeStart") is field,
        quick.window.activeFocusItem().objectName() if quick.window.activeFocusItem() else None,
    )
    assert not quick.warnings


def test_one_off_folder_is_applied_after_confirmation_without_mutating_job(scheduler, monkeypatch, tmp_path):
    from al_media.quick.controller import ApplicationController

    controller = ApplicationController(scheduler, scheduler.preferences, PreviewProvider(), persist=False, tray=False)
    prepared(controller.composer)
    controller.settings.setValue("ask_destination", True)
    captured = []
    monkeypatch.setattr(controller, "_choose", lambda callback, **kwargs: captured.append(callback))
    monkeypatch.setattr(scheduler, "pump", lambda: None)
    controller.composer.download()
    assert captured and not scheduler.tasks
    controller.composer.setMode("audio")
    controller.settings.setValue("name_style", "artist_title")
    captured[0](str(tmp_path / "one-off"))
    task = next(iter(scheduler.tasks.values()))
    assert task.selection == "best"
    assert task.preferences_snapshot["name_style"] == "title"
    assert task.folder == str(tmp_path / "one-off")
    assert scheduler.preferences.folder != task.folder
    controller.dispose()


def test_cancelled_destination_does_not_create_task_or_change_recent_paths(scheduler, monkeypatch):
    from al_media.quick.controller import ApplicationController

    controller = ApplicationController(scheduler, scheduler.preferences, PreviewProvider(), persist=False, tray=False)
    prepared(controller.composer)
    controller.settings.setValue("ask_destination", True)
    before = list(scheduler.preferences.recent_folders)
    callbacks = []
    monkeypatch.setattr(controller, "_choose", lambda callback, **kwargs: callbacks.append(callback))
    controller.composer.download()
    assert callbacks and not scheduler.tasks
    # A cancelled native dialog emits no selected path; no commit runs.
    assert scheduler.preferences.recent_folders == before
    controller.dispose()


def test_playlist_selection_preserves_original_indices_and_snapshot(scheduler):
    composer = ComposerViewModel(scheduler, scheduler.preferences, persist=False)
    source = Task(
        "https://example.test/playlist",
        title="Playlist",
        playlist=True,
        playlist_entries=[
            {"index": 1, "title": "One", "url": "https://example.test/one"},
            {"index": 2, "title": "Unavailable", "url": ""},
            {"index": 3, "title": "Three", "url": "https://example.test/three"},
        ],
    )
    tasks = composer.submissions.playlist(source, [2, 3], scheduler.preferences)
    assert len(tasks) == 1 and tasks[0].playlist_index == 3
    assert tasks[0].playlist_title == "Playlist" and not tasks[0].playlist
    scheduler.preferences.music_cover = False
    assert tasks[0].preferences_snapshot["music_cover"]


def test_native_tray_close_and_explicit_exit(quick, qtbot):
    class Tray:
        def hide(self):
            pass

    controller = quick.controller
    controller.tray = Tray()
    controller.preferences.close_to_tray = True
    quick.window.showMaximized()
    qtbot.wait(30)
    assert not controller.requestClose()
    assert not quick.window.isVisible() and not controller.closing
    controller.restore()
    qtbot.wait(30)
    assert quick.window.isVisible()
    assert quick.window.windowState() == Qt.WindowState.WindowMaximized
    controller.quit()
    qtbot.waitUntil(lambda: controller._exit_ready)
    # The real menu is only created with a real tray; restore isolation for cleanup.
    controller.tray = None


def test_container_preview_matches_progressive_and_separate_streams():
    from al_media.core.metadata import expected_container

    progressive = Task("https://example.test/a", formats=[{"vcodec": "h264", "acodec": "aac", "height": 1080, "ext": "mp4"}])
    assert expected_container(progressive) == "MP4"
    progressive.formats[0]["acodec"] = "none"
    assert expected_container(progressive) == "MKV"
    progressive.selection = "mp3:192"
    assert expected_container(progressive) == "MP3"


def test_late_duration_updates_preview_and_mode_switch_keeps_poster(scheduler, monkeypatch):
    from al_media.quick.media import MediaViewModel

    media = MediaViewModel({}, PreviewProvider())
    values = []
    monkeypatch.setattr(media.extractor, "set_task", lambda task: values.append(task.duration))
    task = Task("https://example.test/direct.mp4")
    media.set_task(task)
    media._source = "image://preview/fixture"
    task.duration = 120
    media.set_task(task)
    task.selection = "mp3:320"
    media.set_task(task)
    assert values == [None, 120, 120]
    assert media.source == "image://preview/fixture"
    media.shutdown()
    assert not media.active


def test_completed_row_displays_actual_bitrate_and_persisted_file_size(scheduler):
    model = DownloadsModel(scheduler, scheduler.preferences)
    task = Task("https://example.test/a", state=State.COMPLETED, selection="mp3:320", output_bitrate=128_000, final_path="D:/Media/Title.mp3", final_size=1_000)
    scheduler.tasks[task.id] = task
    scheduler.changed.emit(task)
    role = next(role for role, name in model.roleNames().items() if name == b"metadata")
    label = model.data(model.index(0), role)
    assert "128" in label and "320" not in label and "1.0" in label and "MP3" in label
    task.selection, task.output_bitrate = "m4a", None
    task.final_path, task.formats = "D:/Media/Title.m4a", INFO["formats"]
    scheduler.changed.emit(task)
    label = model.data(model.index(0), role)
    assert "M4A" in label and "1080p" not in label
    task.selection, task.final_path = "video:720", "D:/Media/Title.mp4"
    scheduler.changed.emit(task)
    label = model.data(model.index(0), role)
    assert "720p" in label and "1080p" not in label


@pytest.mark.parametrize("digits", ["000123", "00:01:23"])
def test_keyboard_range_entry_is_atomic_and_survives_escape(quick, qtbot, digits):
    composer = quick.controller.composer
    prepared(composer)
    composer.toggleRange()
    quick.window.requestActivate()
    qtbot.wait(30)
    item(quick, "rangeStart").forceActiveFocus()
    # Digits advance through hours, minutes and seconds automatically.
    for digit in digits:
        QTest.keyClick(quick.window, Qt.Key.Key_Colon if digit == ":" else Qt.Key(ord(digit)))
    assert composer.state["rangeStart"] == "00:01:23"
    assert item(quick, "rangeStart").property("text") == "00:01:23"
    QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    assert not composer.state["rangeOpen"] and composer.state["rangeStart"] == "00:01:23"
    assert not composer.state["canDownload"]
    assert composer.applyRange()
    assert composer.task.clip_start == 83 and composer.task.clip_end == 120


def test_appearance_controls_keep_geometry_for_every_language_and_theme(quick, qtbot):
    quick.controller.navigate("settings")
    qtbot.wait(30)
    controls = [item(quick, name) for name in ("themePicker", "languagePicker")]
    geometry = [(obj.x(), obj.width(), obj.height()) for obj in controls]
    assert geometry[0][1] == geometry[1][1]
    for language in ("ru", "en", "be", "uk"):
        for theme in ("system", "light", "dark"):
            quick.controller.settings.setValue("language", language)
            quick.controller.settings.setValue("theme", theme)
            qtbot.wait(20)
            assert [(obj.x(), obj.width(), obj.height()) for obj in controls] == geometry
    assert not quick.warnings


@pytest.mark.parametrize("name", ["downloadFolder", "concurrencyField"])
def test_settings_background_click_releases_field_focus(quick, qtbot, name):
    quick.controller.navigate("settings")
    quick.window.requestActivate()
    qtbot.wait(30)
    click(quick, name)
    field = item(quick, name)
    assert field.hasActiveFocus()
    page = item(quick, "settingsPage")
    point = page.mapToScene(QPointF(12, 180)).toPoint()
    QTest.mouseClick(quick.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    assert not field.hasActiveFocus()
    # Clicking between fields must still focus the newly clicked field.
    click(quick, "concurrencyField")
    assert item(quick, "concurrencyField").hasActiveFocus()
    assert not quick.warnings


def test_license_collapse_reclaims_space_and_scrollbar_is_on_right(quick, qtbot):
    quick.controller.navigate("about")
    click(quick, "licensesButton")
    qtbot.wait(220)
    section = item(quick, "mainLicenseSection")
    expanded_height = section.height()
    scroll, bar = item(quick, "licenseScroll"), item(quick, "licenseScrollBar")
    assert expanded_height > 200
    assert bar.mapToScene(QPointF()).x() > scroll.mapToScene(QPointF()).x() + scroll.width() - 20
    QMetaObject.invokeMethod(item(quick, "licenseBodyToggle"), "click")
    qtbot.wait(60)
    assert 45 < section.height() < expanded_height  # Collapse has an actual transition.
    qtbot.wait(180)
    assert section.height() == 45  # Header + rule, without a retained Loader height.
    QMetaObject.invokeMethod(item(quick, "licenseBodyToggle"), "click")
    qtbot.wait(220)
    assert section.height() == expanded_height
    assert not quick.warnings


def test_license_header_responds_to_first_click_while_scrolling(quick, qtbot):
    quick.controller.navigate("about")
    click(quick, "licensesButton")
    qtbot.wait(220)
    pending = [quick.window.contentItem()]
    sections = []
    while pending:
        obj = pending.pop()
        if obj.property("heading") is not None and obj.property("expanded") is not None:
            sections.append(obj)
            obj.setProperty("expanded", True)
        pending.extend(obj.childItems())
    qtbot.wait(220)
    scroll = item(quick, "licenseScroll")
    scroll.setProperty("contentY", 500)
    QMetaObject.invokeMethod(scroll, "flick", Q_ARG(float, 0), Q_ARG(float, -600))
    qtbot.wait(30)
    top = scroll.mapToScene(QPointF()).y()
    candidates = [obj for obj in sections if top + 30 < obj.mapToScene(QPointF()).y() < top + scroll.height() - 80]
    assert candidates
    section = candidates[0]
    point = section.mapToScene(QPointF(120, 22)).toPoint()
    QTest.mouseClick(quick.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    assert not section.property("expanded"), "The first click was consumed by the scrolling container"
    assert not quick.warnings


def test_settings_picker_opens_on_first_click_while_scrolling(quick, qtbot):
    quick.controller.navigate("settings")
    qtbot.wait(30)
    scroll = item(quick, "settingsScroll")
    QMetaObject.invokeMethod(scroll, "flick", Q_ARG(float, 0), Q_ARG(float, -600))
    qtbot.wait(30)
    click(quick, "themePicker")
    assert item(quick, "themePicker").property("menuVisible")
    assert not quick.warnings


def test_analysis_spinner_is_large_and_rotates_with_platform_effects_disabled(quick, qtbot):
    quick.window.setProperty("reducedMotion", True)
    composer = quick.controller.composer
    composer.setUrl("https://example.test/video")
    composer.timer.stop()
    spinner, ring = item(quick, "analysisSpinner"), item(quick, "spinnerRing")
    assert spinner.isVisible() and spinner.width() >= 60 and spinner.height() >= 60
    qtbot.wait(60)
    before = ring.property("rotation")
    qtbot.wait(150)
    assert spinner.property("spinning") and abs(ring.property("rotation") - before) > 10
    composer.setUrl("")
    assert not spinner.isVisible() and not spinner.property("spinning")
    assert not quick.warnings


@pytest.mark.parametrize("name", ["play", "retry", "youtube", "spinner"])
def test_tinted_icons_render_including_svg_with_leading_license_comments(qapp, name):
    provider = IconProvider(Path(__file__).parents[1] / "src/al_media/quick/qml/icons")
    rendered = provider.requestImage(name + "/4f7ef8", QSize(), QSize(32, 32))
    assert any(rendered.pixelColor(x, y).alpha() > 100 for x in range(32) for y in range(32)), name


@pytest.mark.parametrize("state", [State.COMPLETED, State.QUEUED, State.FAILED])
def test_download_row_has_direct_actions_without_details_or_configuration(quick, qtbot, tmp_path, state):
    result = tmp_path / "result.mp4"
    result.write_bytes(b"fixture result")
    task = Task("https://example.test/video", title="File", state=state, final_path=str(result) if state == State.COMPLETED else "")
    scheduler = quick.controller.scheduler
    scheduler.tasks[task.id] = task
    scheduler.changed.emit(task)
    qtbot.wait(50)
    row = item(quick, "downloadRow-" + task.id)
    assert row.height() <= 100
    texts = [obj.property("text") for obj in row.findChildren(QQuickItem)]
    assert "Настроить" not in texts and "Подробнее" not in texts
    remove = item(quick, "removeTask-" + task.id)
    if state == State.QUEUED:
        assert not remove.isVisible()
        assert item(quick, "cancelTask-" + task.id).isVisible()
        click(quick, "cancelTask-" + task.id)
        assert task.state == State.CANCELLED
    elif state == State.COMPLETED:
        button = item(quick, "openResult-" + task.id)
        assert button.isVisible() and not button.property("ghost")
        assert button.property("leftPadding") == button.property("rightPadding") == 14
        assert item(quick, "showFolder-" + task.id).isVisible()
    else:
        assert item(quick, "retryTask-" + task.id).isVisible()
    qtbot.wait(30)
    assert remove.isVisible()
    click(quick, "removeTask-" + task.id)
    assert quick.controller.downloads.count == 0
    assert result.read_bytes() == b"fixture result"
    assert not quick.warnings


def test_empty_and_loading_copy_matches_phase_without_empty_queue(quick, qtbot):
    assert not item(quick, "queueHeading").isVisible()
    assert item(quick, "composerHeading").property("text") == "Скачайте видео или аудио"
    composer = quick.controller.composer
    composer.setUrl("https://example.test/video")
    composer.timer.stop()
    assert item(quick, "composerHeading").property("text") == "Анализируем ссылку…"
    assert "Получаем сведения" in item(quick, "composerHelp").property("text")
    assert not item(quick, "queueHeading").isVisible()
    prepared(composer)
    assert not item(quick, "queueHeading").isVisible()
    task = Task("https://example.test/queued", state=State.DOWNLOADING)
    quick.controller.scheduler.tasks[task.id] = task
    quick.controller.scheduler.changed.emit(task)
    qtbot.wait(30)
    assert item(quick, "queueHeading").isVisible()
    assert not quick.warnings


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_recent_folders_toggle_on_trigger_and_stay_inside_window(quick, qtbot, theme, tmp_path):
    quick.controller.settings.setValue("theme", theme)
    quick.controller.preferences.recent_folders = [str(tmp_path / ("Long folder name " * 8)), str(tmp_path / "Audio")]
    quick.controller.settings.changed.emit()
    quick.controller.navigate("settings")
    qtbot.wait(40)
    button = item(quick, "recentFolders")
    menu = button.findChild(QObject, "recentFoldersMenu")
    assert menu is not None
    for size in ((1280, 720), (1024, 640)):
        quick.window.resize(*size)
        qtbot.wait(30)
        for _ in range(3):
            click(quick, "recentFolders")
            qtbot.waitUntil(lambda: menu.property("visible"))
            qtbot.wait(40)
            assert button.property("selected")
            content = menu.property("contentItem")
            assert content.height() == 96
            for index in range(2):
                icon = item(quick, "recentFolderIcon-" + str(index))
                label = item(quick, "recentFolderPath-" + str(index))
                assert icon.width() == icon.height() == 20
                assert label.width() > 200 and label.height() <= 24
            origin = content.mapToScene(QPointF())
            assert 0 <= origin.x() and origin.x() + content.width() <= size[0]
            assert 0 <= origin.y() and origin.y() + content.height() <= size[1]
            # A second trigger press must not auto-dismiss and reopen on release.
            point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
            QTest.mousePress(quick.window, Qt.MouseButton.LeftButton, pos=point)
            assert menu.property("visible")
            QTest.mouseRelease(quick.window, Qt.MouseButton.LeftButton, pos=point)
            qtbot.wait(220)
            assert not menu.property("visible") and not button.property("selected")
        click(quick, "recentFolders")
        QTest.keyClick(quick.window, Qt.Key.Key_Escape)
        qtbot.waitUntil(lambda: not menu.property("visible"))
        click(quick, "recentFolders")
        QTest.mouseClick(quick.window, Qt.MouseButton.LeftButton, pos=QPointF(size[0] - 16, 130).toPoint())
        qtbot.waitUntil(lambda: not menu.property("visible"))
    assert not quick.warnings


@pytest.mark.parametrize("keyboard", [False, True])
def test_recent_folder_selection_commits_path_and_closes_popup(quick, qtbot, tmp_path, keyboard):
    folders = [tmp_path / "Music", tmp_path / "Videos"]
    for folder in folders:
        folder.mkdir()
    quick.controller.preferences.recent_folders = list(map(str, folders))
    quick.controller.settings.changed.emit()
    quick.controller.navigate("settings")
    qtbot.wait(40)
    button = item(quick, "recentFolders")
    menu = button.findChild(QObject, "recentFoldersMenu")
    click(quick, "recentFolders")
    qtbot.waitUntil(lambda: menu.property("opened"))
    qtbot.wait(50)
    if keyboard:
        QTest.keyClick(quick.window, Qt.Key.Key_Down)
        QTest.keyClick(quick.window, Qt.Key.Key_Return)
    else:
        click(quick, "recentFolder-1")
    qtbot.waitUntil(lambda: not menu.property("visible"))
    assert Path(quick.controller.preferences.folder) == folders[1]
    assert not quick.warnings


def test_settings_has_no_back_to_downloads_link(quick, qtbot):
    quick.controller.navigate("settings")
    qtbot.wait(30)
    assert not any("Назад к загрузкам" in str(obj.property("text") or "") for obj in item(quick, "settingsPage").findChildren(QQuickItem))


def test_disclosure_arrows_animate_open_and_return_when_closed(quick, qtbot):
    quick.window.setProperty("reducedMotion", False)
    quick.controller.navigate("settings")
    quick.controller.preferences.recent_folders.append("D:/Other")
    quick.controller.settings.changed.emit()
    qtbot.wait(30)
    for name in ("themePicker", "recentFolders"):
        control = item(quick, name)
        chevron = next(child for child in control.findChildren(QQuickItem) if child.property("name") == "chevron")
        assert chevron.property("rotation") == 0
        click(quick, name)
        qtbot.wait(60)
        assert 0 < chevron.property("rotation") < 180
        qtbot.wait(160)
        assert chevron.property("rotation") == 180
        QTest.keyClick(quick.window, Qt.Key.Key_Escape)
        qtbot.wait(220)
        assert chevron.property("rotation") == 0
    assert not quick.warnings


def test_time_segments_allow_mouse_editing_and_validate_before_commit(quick, qtbot):
    composer = quick.controller.composer
    prepared(composer)
    composer.toggleRange()
    quick.window.requestActivate()
    qtbot.wait(30)
    click(quick, "rangeStartMinutes")
    for key in (Qt.Key.Key_0, Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3):
        QTest.keyClick(quick.window, key)
    assert composer.state["rangeStart"] == "0:01:23"
    assert item(quick, "rangeStartSeconds").hasActiveFocus()
    assert composer.applyRange() and composer.task.clip_start == 83
    composer.toggleRange()
    click(quick, "rangeEndSeconds")
    for key in (Qt.Key.Key_9, Qt.Key.Key_9):
        QTest.keyClick(quick.window, key)
    assert not composer.applyRange()
    assert composer.task.clip_start == 83 and composer.task.clip_end == 120
    composer.resetRange()
    assert composer.task.clip_start is None and composer.task.clip_end is None
    assert composer.state["rangeStart"] == composer.state["rangeEnd"] == ""
    assert not quick.warnings


def test_invalid_concurrency_has_visible_inline_message(quick, qtbot):
    quick.controller.navigate("settings")
    quick.controller.settings.setConcurrency("6")
    qtbot.wait(30)
    field, message = item(quick, "concurrencyField"), item(quick, "concurrencyError")
    assert field.property("hasError") and message.isVisible()
    assert message.mapToScene(QPointF()).y() < quick.window.height()
    quick.controller.settings.setValue("theme", "light")
    assert field.property("text") == "6" and field.property("hasError")
    assert quick.controller.preferences.concurrency == 3


def test_applying_range_preserves_inflight_probe_identity_and_revalidates_late_bounds(scheduler):
    composer = ComposerViewModel(scheduler, scheduler.preferences, persist=False)
    original = prepared(composer)
    original.duration = None
    composer.editRange("start", "0:10")
    composer.editRange("end", "0:20")
    assert composer.applyRange()
    assert composer.task is original
    original.duration = 15
    composer._probed(original)
    assert composer.state["duration"] == "0:15"
    assert composer.state["rangeEnd"] == "0:20"
    assert composer.state["rangeError"] == "clip_invalid" and not composer.state["canDownload"]
    composer.resetRange()
    assert composer.state["canDownload"]


def test_audio_track_change_filters_formats_and_audio_mode_uses_sidecar_subtitles(scheduler):
    composer = ComposerViewModel(scheduler, scheduler.preferences, persist=False)
    task = prepared(composer)
    task.formats[2]["language"] = "en"
    task.formats.append({"format_id": "a2", "vcodec": "none", "acodec": "opus", "ext": "webm", "language": "ru"})
    task.audio_tracks = [{"label": "English", "language": "en", "ids": ["a1"]}, {"label": "Russian", "language": "ru", "ids": ["a2"]}]
    composer.setMode("audio")
    composer.setAudioFormat("m4a")
    assert task.selection == "m4a"
    composer.setExtra("track", "1")
    assert task.selection == "audio" and task.audio_track_ids == ["a2"]
    assert "m4a" not in {item["value"] for item in composer.state["audioFormats"]}
    composer.setMode("video")
    task.subtitle_mode, task.subtitle_language = "embedded", "en"
    composer.setMode("audio")
    assert task.subtitle_mode == "sidecar"


def test_new_preferences_round_trip_through_native_settings_store(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    import al_media.config as config

    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(config, "settings_store", lambda: QSettings(path, QSettings.Format.IniFormat))
    folder = str(tmp_path / "Downloads")
    prefs = Preferences(folder=folder, ask_destination=True, recent_folders=[folder, str(tmp_path / "Audio")])
    prefs.save()
    restored = Preferences.load()
    assert restored.ask_destination and restored.recent_folders == prefs.recent_folders
    assert restored.folder == folder and restored.concurrency == 3
