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
from al_media.quick.localization import text
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


def test_mode_changes_do_not_deep_copy_source_metadata(scheduler, monkeypatch):
    composer = ComposerViewModel(scheduler, scheduler.preferences, persist=False)
    source = prepared(composer)
    source.automatic_captions = {f"lang-{i}": [{"url": "https://example.test/" + "x" * 2000}] for i in range(500)}

    def forbidden_copy():
        raise AssertionError("A mode change copied all source metadata")

    monkeypatch.setattr(source, "to_dict", forbidden_copy)
    composer.setMode("audio")
    composer.select("mp3:192")
    composer.setMode("video")
    assert composer.state["mode"] == "video"
    assert "formats" not in next(iter(composer._drafts.values()))["task"]
    composer.shutdown()


def test_slow_selection_saving_does_not_block_switching_and_latest_choice_wins(scheduler, qtbot, monkeypatch):
    from time import monotonic, sleep

    from PySide6.QtCore import QSettings, QTimer

    from al_media.quick.viewmodels import composer as module

    saved, ticks = {}, []

    class Store:
        def setValue(self, key, value):
            saved[key] = value

        def sync(self):
            sleep(0.25)

        def status(self):
            return QSettings.Status.NoError

    monkeypatch.setattr(module, "settings_store", Store)
    composer = ComposerViewModel(scheduler, scheduler.preferences, persist=True)
    prepared(composer)
    heartbeat = QTimer(interval=10)
    heartbeat.timeout.connect(lambda: ticks.append(monotonic()))
    heartbeat.start()
    try:
        start = monotonic()
        composer.setMode("audio")
        assert monotonic() - start < 0.15
        qtbot.waitUntil(lambda: composer._saving)
        composer.setMode("video")
        composer.setMode("audio")
        composer.select("mp3:128")
        composer.shutdown()  # Must flush the latest choice even before debounce.
        qtbot.waitUntil(lambda: not composer.busy, timeout=4000)
        assert saved["media_mode"] == "audio" and saved["mp3_bitrate"] == 128
        assert set(saved) == {"media_mode", "video_quality", "audio_format", "mp3_bitrate"}
        assert len(ticks) > 10
        assert max(b - a for a, b in zip(ticks, ticks[1:], strict=False)) < 0.15
    finally:
        heartbeat.stop()
        composer.shutdown()
        qtbot.waitUntil(lambda: not composer.busy, timeout=4000)


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


def test_download_details_always_have_rate_and_eta_but_not_after_cancel(scheduler):
    model = DownloadsModel(scheduler, scheduler.preferences)
    task = Task("https://example.test/video", state=State.DOWNLOADING)
    record = model._record(task)
    assert record["detail"] == "0 МБ/с" and record["indeterminate"]
    task.speed, task.eta, task.percent = 100_000, 20, 5
    record = model._record(task)
    assert record["detail"] == "0.10 МБ/с · ≈ 0:20" and not record["indeterminate"]
    task.state, task.error = State.CANCELLED, "cancelled"
    record = model._record(task)
    assert not record["detail"] and not record["error"] and not record["indeterminate"]
    for state in (State.QUEUED, State.PENDING_METADATA, State.READY):
        task.state, task.percent = state, None
        assert not model._record(task)["indeterminate"]


@pytest.mark.parametrize("stage,label", [("merging", "Объединение дорожек"), ("converting", "Преобразование аудио"),
                                       ("tagging", "Добавление тегов и обложки"), ("embedding_subtitles", "Добавление субтитров"),
                                       ("verifying", "Проверка файла"), ("", "Завершение обработки")])
def test_download_stage_labels_follow_real_pipeline(scheduler, stage, label, tmp_path):
    model = DownloadsModel(scheduler, scheduler.preferences)
    task = Task("https://example.test/video", state=State.DOWNLOADING)
    assert model._record(task)["status"] == "Подготовка скачивания"
    task.percent = 0
    assert model._record(task)["status"] == "Скачивание"
    task.state, task.processing_stage = State.POSTPROCESSING, stage
    assert model._record(task)["status"] == label
    task.state = State.COMPLETED
    output = tmp_path / "finished.mkv"
    output.write_bytes(b"fixture")
    task.final_path = str(output)
    assert model._record(task)["status"] == "Готово"


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
    if name == "licensesButton":
        scroll = item(quick, "aboutScroll")
        top = obj.mapToScene(QPointF()).y()
        viewport_top = scroll.mapToScene(QPointF()).y()
        offset = min(0, top - viewport_top) + max(0, top + obj.height() - viewport_top - scroll.height())
        scroll.setProperty("contentY", max(0, min(scroll.property("contentY") + offset, scroll.property("contentHeight") - scroll.height())))
        QTest.qWait(30)
    p = obj.mapToScene(QPointF(obj.width() / 2, obj.height() / 2)).toPoint()
    QTest.mouseClick(quick.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)


@pytest.mark.parametrize("page,bar_name", [("settings", "settingsScrollBar"), ("downloads", "downloadsScrollBar")])
def test_edge_scrollbar_keeps_hit_area_and_expands_thumb_on_hover(quick, qtbot, page, bar_name):
    if page == "downloads":
        for i in range(12):
            task = Task(f"https://example.test/{i}", title="File", state=State.COMPLETED)
            quick.controller.scheduler.tasks[task.id] = task
            quick.controller.scheduler.changed.emit(task)
    quick.controller.navigate(page)
    qtbot.wait(80)
    bar = item(quick, bar_name)
    thumb = bar.findChild(QQuickItem, "scrollThumb")
    point = bar.mapToScene(QPointF())
    assert abs(point.x() + bar.width() - quick.window.width()) < 0.01
    assert bar.width() == 14
    QTest.mouseMove(quick.window, QPointF(200, 100).toPoint())
    qtbot.wait(180)
    assert thumb.width() == 4
    center = thumb.mapToScene(QPointF(thumb.width() / 2, thumb.height() / 2)).toPoint()
    QTest.mouseMove(quick.window, center)
    qtbot.wait(180)
    assert bar.property("hovered") and thumb.width() == 10
    assert bar.width() == 14  # Expansion does not move content or its hit area.
    QTest.mouseMove(quick.window, QPointF(200, 100).toPoint())
    qtbot.wait(180)
    assert thumb.width() == 4
    scroll = item(quick, "settingsScroll" if page == "settings" else "downloadsScroll")
    previous = scroll.property("contentY")
    center = thumb.mapToScene(QPointF(thumb.width() / 2, thumb.height() / 2)).toPoint()
    QTest.mouseMove(quick.window, center)
    QTest.mousePress(quick.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
    QTest.mouseMove(quick.window, center + QPointF(0, 60).toPoint(), delay=40)
    QTest.mouseRelease(quick.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center + QPointF(0, 60).toPoint())
    qtbot.wait(50)
    assert scroll.property("contentY") > previous
    assert not quick.warnings


def test_unknown_progress_becomes_left_aligned_percentage_across_state_changes(quick, qtbot):
    scheduler = quick.controller.scheduler
    task = Task("https://example.test/video", title="Progress", state=State.DOWNLOADING)
    scheduler.tasks[task.id] = task
    scheduler.changed.emit(task)
    qtbot.wait(130)
    bar = item(quick, "taskProgress-" + task.id)
    assert bar.property("spinning")
    task.percent = 5
    scheduler.changed.emit(task)
    qtbot.wait(150)
    fill = bar.findChild(QQuickItem, "determinateFill")
    assert fill.isVisible() and not bar.property("spinning")
    assert fill.x() == 0 and abs(fill.width() - bar.width() * 0.05) < 0.01
    qtbot.wait(150)
    assert fill.x() == 0
    task.state, task.percent = State.QUEUED, None
    scheduler.changed.emit(task)
    qtbot.wait(30)
    assert not bar.property("spinning") and fill.width() == 0
    task.state = State.POSTPROCESSING
    scheduler.changed.emit(task)
    qtbot.wait(80)
    assert bar.property("spinning")
    task.state, task.percent = State.DOWNLOADING, 63
    scheduler.changed.emit(task)
    qtbot.wait(50)
    assert not bar.property("spinning")
    assert fill.x() == 0 and abs(fill.width() - bar.width() * 0.63) < 0.01
    assert not quick.warnings


def test_mode_highlight_moves_smoothly_without_overlapping_hover_regions(quick, qtbot):
    quick.window.setProperty("reducedMotion", False)
    composer = quick.controller.composer
    prepared(composer)
    qtbot.wait(200)
    highlight = item(quick, "modeHighlight")
    video, audio = item(quick, "videoMode"), item(quick, "audioMode")
    assert audio.x() - (video.x() + video.width()) == 4
    start = highlight.x()
    composer.setMode("audio")
    # Observe an intermediate frame rather than assuming the Windows render
    # thread has drawn one within a fixed 35 ms on every run.
    qtbot.waitUntil(lambda: start < highlight.x() < highlight.width() + 8)
    qtbot.waitUntil(lambda: abs(highlight.x() - highlight.width() - 8) < 0.001)
    assert not quick.warnings


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("page,bar_name", [("settings", "settingsScrollBar"), ("downloads", "downloadsScrollBar")])
def test_edge_scrollbar_arrows_hold_wheel_and_thumb_stay_within_track(quick, qtbot, theme, page, bar_name):
    from PySide6.QtCore import QCoreApplication, QPoint
    from PySide6.QtGui import QWheelEvent

    for i in range(12):
        task = Task(f"https://example.test/{i}", title="File", state=State.COMPLETED)
        quick.controller.scheduler.tasks[task.id] = task
        quick.controller.scheduler.changed.emit(task)
    quick.controller.settings.setValue("theme", theme)
    quick.controller.navigate(page)
    qtbot.wait(80)
    bar = item(quick, bar_name)
    scroll = item(quick, "settingsScroll" if page == "settings" else "downloadsScroll")
    def child(name):
        pending = [bar]
        while pending:
            candidate = pending.pop()
            if candidate.objectName() == name:
                return candidate
            pending.extend(candidate.childItems())
        raise AssertionError(name)

    up, down = child("scrollUp"), child("scrollDown")
    thumb = bar.findChild(QQuickItem, "scrollThumb")
    assert not up.property("canMove") and down.property("canMove")
    start = scroll.property("contentY")
    point = down.mapToScene(QPointF(down.width() / 2, down.height() / 2)).toPoint()
    QTest.mouseClick(quick.window, Qt.MouseButton.LeftButton, pos=point)
    qtbot.wait(25)
    after_click = scroll.property("contentY")
    assert after_click > start
    QTest.mousePress(quick.window, Qt.MouseButton.LeftButton, pos=point)
    qtbot.wait(570)
    QTest.mouseRelease(quick.window, Qt.MouseButton.LeftButton, pos=point)
    assert scroll.property("contentY") > after_click + 40

    # Both pixel-based touchpads and angle-based mouse wheels over the thumb.
    for pixels, angle in ((QPoint(0, -50), QPoint()), (QPoint(), QPoint(0, -120))):
        before = scroll.property("contentY")
        pos = thumb.mapToScene(QPointF(thumb.width() / 2, thumb.height() / 2))
        event = QWheelEvent(pos, QPointF(quick.window.mapToGlobal(pos.toPoint())), pixels, angle,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QCoreApplication.sendEvent(quick.window, event)
        qtbot.waitUntil(lambda: not bar.property("wheelAnimating"))
        assert scroll.property("contentY") > before
    for end in (0.0, 1.0):
        bar.setProperty("position", end)
        qtbot.wait(30)
        top = thumb.mapToItem(bar, QPointF()).y()
        assert top >= up.y() + up.height() + 1
        assert top + thumb.height() <= down.y() - 1
    assert not down.property("canMove") and up.property("canMove")
    point = up.mapToScene(QPointF(up.width() / 2, up.height() / 2)).toPoint()
    before = scroll.property("contentY")
    QTest.mouseClick(quick.window, Qt.MouseButton.LeftButton, pos=point)
    assert scroll.property("contentY") < before
    before = scroll.property("contentY")
    pos = thumb.mapToScene(QPointF(thumb.width() / 2, thumb.height() / 2))
    QCoreApplication.sendEvent(quick.window, QWheelEvent(pos, QPointF(quick.window.mapToGlobal(pos.toPoint())), QPoint(), QPoint(0, 120),
                                                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
    qtbot.waitUntil(lambda: not bar.property("wheelAnimating"))
    assert scroll.property("contentY") < before
    assert not quick.warnings


def test_mode_switch_is_immediate_after_first_source_and_reverses_mid_animation(quick, qtbot):
    quick.window.setProperty("reducedMotion", False)
    composer = quick.controller.composer
    composer.setUrl("https://example.test/video")
    composer.timer.stop()
    prepared(composer)
    click(quick, "audioMode")
    assert item(quick, "audioMode").property("selected")
    qtbot.waitUntil(lambda: composer.state["mode"] == "audio")
    qtbot.wait(45)
    highlight = item(quick, "modeHighlight")
    halfway = highlight.x()
    assert 4 < halfway < highlight.width() + 8
    click(quick, "videoMode")
    assert item(quick, "videoMode").property("selected")
    assert abs(highlight.x() - halfway) < 1
    qtbot.waitUntil(lambda: composer.state["mode"] == "video")
    qtbot.wait(230)
    assert highlight.x() == 4
    assert not quick.warnings


@pytest.mark.parametrize("page,scroll_name", [("downloads", "downloadsScroll"), ("settings", "settingsScroll"), ("about", "aboutScroll")])
@pytest.mark.parametrize("touchpad", [False, True])
def test_empty_page_gutters_scroll_in_both_directions(quick, qtbot, page, scroll_name, touchpad):
    from time import monotonic

    from PySide6.QtCore import QCoreApplication, QPoint
    from PySide6.QtGui import QInputDevice, QPointingDevice, QWheelEvent

    for i in range(16):
        task = Task(f"https://example.test/gutter/{i}", title="Downloaded file", state=State.COMPLETED)
        quick.controller.scheduler.tasks[task.id] = task
        quick.controller.scheduler.changed.emit(task)
    if page == "about":
        quick.window.setMinimumHeight(400)
    quick.window.resize(1920, 400 if page == "about" else 700)
    quick.controller.navigate(page)
    qtbot.wait(80)
    scroll = item(quick, scroll_name)
    surface = item(quick, page + "Page")
    assert scroll.width() == surface.width() and scroll.height() == surface.height()
    inset = quick.window.property("contentInset")
    points = [QPointF(inset / 2, surface.height() / 2), QPointF(surface.width() - max(18, inset / 2), surface.height() / 2),
              QPointF(surface.width() / 2, 8), QPointF(surface.width() / 2, surface.height() - 8)]
    device = QPointingDevice("Test touchpad", 101, QInputDevice.DeviceType.TouchPad, QPointingDevice.PointerType.Finger,
                             QInputDevice.Capability.Position | QInputDevice.Capability.PixelScroll, 2, 0) if touchpad else None
    bar = item(quick, {"downloads": "downloadsScrollBar", "settings": "settingsScrollBar", "about": "aboutScrollBar"}[page])

    def send(local, amount):
        position = surface.mapToScene(local)
        global_position = QPointF(quick.window.mapToGlobal(position.toPoint()))
        if touchpad:
            frames = [(0, Qt.ScrollPhase.ScrollBegin), *[(amount // 3, Qt.ScrollPhase.ScrollUpdate), (0, Qt.ScrollPhase.ScrollUpdate)] * 3,
                      (0, Qt.ScrollPhase.ScrollEnd)]
            for delta, phase in frames:
                angle = QPoint(0, amount * 2) if delta == 0 and phase == Qt.ScrollPhase.ScrollUpdate else QPoint()
                event = QWheelEvent(position, global_position, QPoint(0, delta), angle, Qt.MouseButton.NoButton,
                                    Qt.KeyboardModifier.NoModifier, phase, False, Qt.MouseEventSource.MouseEventSynthesizedBySystem, device)
                event.setTimestamp(int(monotonic() * 1000))
                QCoreApplication.sendEvent(quick.window, event)
                qtbot.wait(16)
        else:
            event = QWheelEvent(position, global_position, QPoint(), QPoint(0, amount * 2), Qt.MouseButton.NoButton,
                                Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
            event.setTimestamp(int(monotonic() * 1000))
            QCoreApplication.sendEvent(quick.window, event)

    for point in points:
        QMetaObject.invokeMethod(scroll, "cancelFlick")
        scroll.setProperty("contentY", scroll.property("originY") - scroll.property("topMargin"))
        qtbot.wait(20)
        before = scroll.property("contentY")
        send(point, -60)
        qtbot.waitUntil(lambda baseline=before: scroll.property("contentY") > baseline + 1, timeout=1000)
        if touchpad:
            last = scroll.property("originY") + scroll.property("contentHeight") - scroll.height() + scroll.property("bottomMargin")
            assert abs(scroll.property("contentY") - min(last, before + 60)) < 1
        qtbot.waitUntil(lambda: not bar.property("wheelAnimating"), timeout=2000)
        qtbot.waitUntil(lambda: not scroll.property("moving"), timeout=2000)
        before = scroll.property("contentY")
        send(point, 60)
        qtbot.waitUntil(lambda baseline=before: scroll.property("contentY") < baseline - 1, timeout=1000)
        qtbot.waitUntil(lambda: not bar.property("wheelAnimating"), timeout=2000)
        qtbot.waitUntil(lambda: not scroll.property("moving"), timeout=2000)
    assert not quick.warnings


@pytest.mark.parametrize("page,bar_name", [("settings", "settingsScrollBar"), ("downloads", "downloadsScrollBar")])
def test_scrollbar_arrow_release_does_not_keep_scrolling_or_reverse_later_wheel(quick, qtbot, page, bar_name):
    from PySide6.QtCore import QPoint

    for i in range(20):
        task = Task(f"https://example.test/{i}", title="File", state=State.COMPLETED)
        quick.controller.scheduler.tasks[task.id] = task
        quick.controller.scheduler.changed.emit(task)
    quick.controller.navigate(page)
    qtbot.wait(80)
    bar = item(quick, bar_name)
    scroll = item(quick, "settingsScroll" if page == "settings" else "downloadsScroll")
    arrows = {}
    pending = [bar]
    while pending:
        candidate = pending.pop()
        arrows[candidate.objectName()] = candidate
        pending.extend(candidate.childItems())
    for _ in range(3):
        for direction in ("scrollDown", "scrollUp"):
            arrow = arrows[direction]
            point = arrow.mapToScene(QPointF(arrow.width() / 2, arrow.height() / 2)).toPoint()
            QTest.mouseMove(quick.window, point)
            QTest.mousePress(quick.window, Qt.MouseButton.LeftButton, pos=point)
            qtbot.wait(500)
            QTest.mouseRelease(quick.window, Qt.MouseButton.LeftButton, pos=point)
            stopped = scroll.property("contentY")
            qtbot.wait(500)
            assert abs(scroll.property("contentY") - stopped) < 1, "An arrow kept repeating after release"
        # A wheel over regular content must keep the new position too.
        pos = scroll.mapToScene(QPointF(scroll.width() / 2, scroll.height() / 2))
        QTest.mouseMove(quick.window, pos.toPoint())
        before = scroll.property("contentY")
        QTest.wheelEvent(quick.window, pos, QPoint(0, -120))
        qtbot.wait(600)
        assert scroll.property("contentY") > before, "A stale scrollbar input pulled content back up"
    assert not quick.warnings


def scroll_surface(quick, qtbot, page):
    if page == "downloads":
        for i in range(20):
            task = Task(f"https://example.test/{i}", title="File", state=State.COMPLETED)
            quick.controller.scheduler.tasks[task.id] = task
            quick.controller.scheduler.changed.emit(task)
    quick.controller.navigate("about" if page == "licenses" else page)
    if page == "licenses":
        QMetaObject.invokeMethod(quick.window, "showLicenses")
        qtbot.waitUntil(lambda: quick.window.findChild(QObject, "licensesDialog").property("opened"))
    qtbot.wait(50)
    names = {"downloads": ("downloadsScrollBar", "downloadsScroll"), "settings": ("settingsScrollBar", "settingsScroll"),
             "licenses": ("licenseScrollBar", "licenseScroll")}
    bar, scroll = (item(quick, name) for name in names[page])
    parts, pending = {}, [bar]
    while pending:
        candidate = pending.pop()
        parts[candidate.objectName()] = candidate
        pending.extend(candidate.childItems())
    return bar, scroll, parts


def send_scroll_wheel(quick, position, delta=-120, *, pixels=0):
    from time import monotonic

    from PySide6.QtCore import QCoreApplication, QPoint
    from PySide6.QtGui import QWheelEvent

    QTest.mouseMove(quick.window, position.toPoint())
    # Deliver logical window coordinates directly. QTest.wheelEvent feeds the
    # platform interface, which scales them again on Windows with display DPI.
    event = QWheelEvent(position, QPointF(quick.window.mapToGlobal(position.toPoint())), QPoint(0, pixels), QPoint(0, delta),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    event.setTimestamp(int(monotonic() * 1000))
    QCoreApplication.sendEvent(quick.window, event)


@pytest.mark.parametrize("page", ["downloads", "settings", "licenses"])
def test_wheel_animation_accumulates_reverses_and_yields_to_precise_input(quick, qtbot, page):
    from time import monotonic

    from PySide6.QtCore import QCoreApplication, QPoint
    from PySide6.QtGui import QWheelEvent

    quick.window.setProperty("reducedMotion", False)
    bar, scroll, parts = scroll_surface(quick, qtbot, page)
    position = scroll.mapToScene(QPointF(scroll.width() / 2, scroll.height() / 2))

    def send(delta=-120, pixels=0):
        event = QWheelEvent(position, QPointF(quick.window.mapToGlobal(position.toPoint())), QPoint(0, pixels), QPoint(0, delta),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        event.setTimestamp(int(monotonic() * 1000))
        QCoreApplication.sendEvent(quick.window, event)

    start = scroll.property("contentY")
    send()
    assert bar.property("wheelAnimating")
    qtbot.wait(32)
    intermediate = scroll.property("contentY")
    assert start < intermediate < start + 72, "A notch must animate through intermediate offsets"
    send()
    qtbot.waitUntil(lambda: not bar.property("wheelAnimating"))
    assert abs(scroll.property("contentY") - start - 144) < 1, "Rapid notches must retain their total distance"

    send()
    qtbot.wait(32)
    turning = scroll.property("contentY")
    send(120)
    qtbot.waitUntil(lambda: not bar.property("wheelAnimating"))
    assert abs(scroll.property("contentY") - (turning - 72)) < 1

    send()
    qtbot.wait(32)
    precise_start = scroll.property("contentY")
    send(0, pixels=-25)
    assert not bar.property("wheelAnimating")
    assert abs(scroll.property("contentY") - precise_start - 25) < 1
    stopped = scroll.property("contentY")
    qtbot.wait(200)
    assert abs(scroll.property("contentY") - stopped) < 1, "A cancelled animation must not resume"

    send()
    qtbot.wait(32)
    up = parts["scrollUp"]
    arrow_center = up.mapToScene(QPointF(up.width() / 2, up.height() / 2)).toPoint()
    QTest.mouseMove(quick.window, scroll.mapToScene(QPointF(60, 60)).toPoint(), delay=0)
    QTest.mouseMove(quick.window, arrow_center)
    qtbot.wait(16)
    assert up.isVisible()
    before_arrow = scroll.property("contentY")
    QTest.mouseClick(quick.window, Qt.MouseButton.LeftButton, pos=arrow_center, delay=0)
    assert not bar.property("wheelAnimating")
    assert abs(scroll.property("contentY") - before_arrow + 40) < 1
    stopped = scroll.property("contentY")
    qtbot.wait(200)
    assert abs(scroll.property("contentY") - stopped) < 1

    quick.window.setProperty("reducedMotion", True)
    before = scroll.property("contentY")
    send(120)
    assert not bar.property("wheelAnimating")
    assert abs(scroll.property("contentY") - max(start, before - 72)) < 1
    assert not quick.warnings


def test_folder_uses_no_default_context_menu_and_source_menu_still_works(quick, qtbot):
    quick.controller.navigate("settings")
    qtbot.wait(50)
    field = item(quick, "downloadFolder")
    center = field.mapToScene(QPointF(field.width() / 2, field.height() / 2)).toPoint()
    QTest.mouseClick(quick.window, Qt.MouseButton.RightButton, pos=center)
    qtbot.wait(50)
    assert not any(obj.inherits("QQuickMenu") and obj.property("visible") for obj in quick.window.findChildren(QObject))
    field.forceActiveFocus()
    QTest.keyClick(quick.window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(quick.window, Qt.Key.Key_D)
    assert field.property("text") == "d"
    QTest.keyClick(quick.window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert field.property("text") != "d"
    QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    quick.controller.navigate("downloads")
    qtbot.wait(50)
    source = item(quick, "sourceUrl")
    center = source.mapToScene(QPointF(source.width() / 2, source.height() / 2)).toPoint()
    QTest.mouseClick(quick.window, Qt.MouseButton.RightButton, pos=center)
    menu = quick.window.findChild(QObject, "sourceContextMenu")
    qtbot.waitUntil(lambda: menu.property("visible"))
    assert menu.property("count") == 2
    QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not menu.property("visible"))
    assert not quick.warnings


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("page", ["downloads", "settings", "licenses"])
def test_scrollbar_arrows_reveal_only_on_hover_without_moving_track(quick, qtbot, theme, page):
    quick.controller.settings.setValue("theme", theme)
    bar, scroll, parts = scroll_surface(quick, qtbot, page)
    thumb, up, down = (parts[name] for name in ("scrollThumb", "scrollUp", "scrollDown"))
    outside = scroll.mapToScene(QPointF(60, 60))
    QTest.mouseMove(quick.window, outside.toPoint())
    qtbot.wait(180)
    assert not up.isVisible() and not down.isVisible() and thumb.width() == 4
    old_top, old_height = thumb.mapToItem(bar, QPointF()).y(), thumb.height()
    pos = bar.mapToScene(QPointF(bar.width() / 2, bar.height() / 2))
    QTest.mouseMove(quick.window, pos.toPoint())
    qtbot.wait(180)
    assert up.isVisible() and down.isVisible() and thumb.width() == 10
    assert thumb.mapToItem(bar, QPointF()).y() == old_top and thumb.height() == old_height
    assert up.height() <= old_top and old_top + old_height <= down.y()
    QTest.mouseMove(quick.window, outside.toPoint())
    qtbot.wait(180)
    assert not up.isVisible() and not down.isVisible() and thumb.width() == 4
    assert not quick.warnings


@pytest.mark.parametrize("page", ["downloads", "settings", "licenses"])
@pytest.mark.parametrize("scenario", ["boundary", "leave_while_held", "drag_resize", "hide_while_held"])
def test_scrollbar_mixed_inputs_never_latch_or_reverse(quick, qtbot, page, scenario):
    bar, scroll, parts = scroll_surface(quick, qtbot, page)
    up, down, thumb = (parts[name] for name in ("scrollUp", "scrollDown", "scrollThumb"))

    def center(obj):
        return obj.mapToScene(QPointF(obj.width() / 2, obj.height() / 2))

    def hold_arrow(arrow, pause=80):
        pos = center(arrow).toPoint()
        QTest.mouseMove(quick.window, pos)
        QTest.mousePress(quick.window, Qt.MouseButton.LeftButton, pos=pos)
        qtbot.wait(pause)
        return pos

    if scenario == "boundary":
        # Reach a boundary while still pressed, then release there. Repeat in
        # both directions, including a press on the already disabled arrow.
        for arrow, at_end in ((down, True), (up, False)):
            first = scroll.property("originY") - scroll.property("topMargin")
            last = max(first, scroll.property("originY") + scroll.property("contentHeight") - scroll.height() + scroll.property("bottomMargin"))
            scroll.setProperty("contentY", last - 4 if at_end else first + 4)
            pos = hold_arrow(arrow, 500)
            QTest.mouseRelease(quick.window, Qt.MouseButton.LeftButton, pos=pos)
            assert not arrow.property("canMove") and not bar.property("pressed")
            pos = hold_arrow(arrow)
            QTest.mouseRelease(quick.window, Qt.MouseButton.LeftButton, pos=pos)
    elif scenario == "leave_while_held":
        hold_arrow(down)
        outside = scroll.mapToScene(QPointF(50, 50)).toPoint()
        QTest.mouseMove(quick.window, outside)
        stopped = scroll.property("contentY")
        qtbot.wait(500)
        assert abs(scroll.property("contentY") - stopped) < 1
        QTest.mouseRelease(quick.window, Qt.MouseButton.LeftButton, pos=outside)
    elif scenario == "drag_resize":
        pos = hold_arrow(down)
        QTest.mouseRelease(quick.window, Qt.MouseButton.LeftButton, pos=pos)
        pos = center(thumb).toPoint()
        QTest.mouseMove(quick.window, pos)
        QTest.mousePress(quick.window, Qt.MouseButton.LeftButton, pos=pos)
        QTest.mouseMove(quick.window, pos + QPointF(0, 50).toPoint(), delay=40)
        QTest.mouseRelease(quick.window, Qt.MouseButton.LeftButton, pos=pos + QPointF(0, 50).toPoint())
        quick.window.resize(1024, 700)
        qtbot.wait(80)
        quick.window.resize(1280, 720)
        qtbot.wait(80)
    else:
        pos = hold_arrow(down)
        quick.window.hide()
        qtbot.wait(450)
        QTest.mouseRelease(quick.window, Qt.MouseButton.LeftButton, pos=pos)
        quick.window.show()
        qtbot.wait(100)

    assert not up.property("repeatAllowed") and not down.property("repeatAllowed")
    first = scroll.property("originY") - scroll.property("topMargin")
    scroll.setProperty("contentY", first)
    # Mix regular wheel, touchpad pixels and wheel over each arrow/track. Wait
    # beyond the repeat delay each time to detect a delayed jump backwards.
    for target, pixels in ((scroll, 0), (bar, -30), (down, 0), (up, 0), (scroll, 0)):
        before = scroll.property("contentY")
        pos = center(target)
        send_scroll_wheel(quick, pos, delta=-30, pixels=pixels)
        qtbot.wait(550)
        assert scroll.property("contentY") > before, (page, scenario, target.objectName())
        assert not bar.property("pressed")
    assert not quick.warnings


def test_queue_columns_and_bulk_actions_keep_files_and_clear_cancelled_rows(quick, qtbot, tmp_path, monkeypatch):
    scheduler = quick.controller.scheduler
    monkeypatch.setattr(scheduler, "pump", lambda: None)
    output = tmp_path / "saved.mp4"
    output.write_bytes(b"keep this download")
    tasks = [Task("https://example.test/" + str(i), title="File", state=state,
                  final_path=str(output) if state == State.COMPLETED else "")
             for i, state in enumerate((State.COMPLETED, State.FAILED, State.QUEUED, State.PENDING_METADATA))]
    for task in tasks:
        scheduler.tasks[task.id] = task
        scheduler.changed.emit(task)
    qtbot.wait(80)
    columns = [item(quick, "statusColumn-" + t.id) for t in tasks]
    assert len({round(c.mapToScene(QPointF()).x(), 2) for c in columns}) == 1
    assert len({round(c.width(), 2) for c in columns}) == 1
    assert quick.controller.downloads.clearableCount == quick.controller.downloads.activeCount == 2
    assert item(quick, "cancelAll").height() == item(quick, "clearCompleted").height()
    quick.controller.clearCompleted()
    qtbot.wait(40)
    assert quick.controller.downloads.count == 2
    assert output.read_bytes() == b"keep this download"
    quick.controller.cancelAll()
    qtbot.wait(50)
    assert quick.controller.downloads.activeCount == 0
    assert quick.controller.downloads.clearableCount == 2
    assert item(quick, "clearCompleted").isVisible()
    assert not item(quick, "cancelAll").isVisible()
    quick.controller.clearCompleted()
    assert quick.controller.downloads.count == 0
    assert output.is_file()
    assert not quick.warnings


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_track_options_stay_visible_disabled_with_hover_explanation(quick, qtbot, theme):
    quick.controller.settings.setValue("theme", theme)
    composer = quick.controller.composer
    prepared(composer)
    qtbot.wait(60)
    button = item(quick, "tracksButton")
    dialog = quick.window.findChild(QObject, "tracksDialog")
    tooltip = quick.window.findChild(QObject, "tracksUnavailableTip")
    assert button.isVisible() and not button.isEnabled()
    assert button.opacity() < 0.5
    assert button.property("tip") == ""
    assert button.height() == item(quick, "cropButton").height() == 36
    point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
    QTest.mouseMove(quick.window, QPointF(10, 10).toPoint())
    qtbot.wait(20)
    QTest.mouseMove(quick.window, point)
    qtbot.waitUntil(lambda: tooltip.property("visible"), timeout=2000)
    assert tooltip.property("text") == "Нет дополнительных дорожек и субтитров"
    click(quick, "tracksButton")
    assert not dialog.property("visible")
    before = button.mapToScene(QPointF())
    composer.task.subtitles = {"ru": [{"ext": "vtt"}]}
    composer.changed.emit()
    qtbot.wait(40)
    assert button.isVisible() and button.isEnabled() and button.opacity() == 1
    assert button.property("tip") == "Дорожки и субтитры"
    assert button.mapToScene(QPointF()) == before
    assert not tooltip.property("visible")
    click(quick, "tracksButton")
    qtbot.waitUntil(lambda: dialog.property("visible"))
    QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    assert not quick.warnings


@pytest.mark.parametrize("available", ["none", "single_track", "tracks", "subtitles", "captions"])
def test_track_options_enable_for_either_tracks_or_subtitles(quick, qtbot, available):
    composer = quick.controller.composer
    prepared(composer)
    composer.task.audio_tracks = []
    if available in {"single_track", "tracks"}:
        composer.task.audio_tracks = [{"label": "Original", "language": "en", "ids": ["a1"]}]
    if available == "tracks":
        composer.task.audio_tracks.append({"label": "Dub", "language": "ru", "ids": ["a2"]})
    if available == "subtitles":
        composer.task.subtitles = {"ru": [{"ext": "vtt"}]}
    if available == "captions":
        composer.task.automatic_captions = {"en": [{"ext": "vtt"}]}
    composer.changed.emit()
    qtbot.wait(50)
    button = item(quick, "tracksButton")
    assert button.isVisible()
    assert button.isEnabled() == (available in {"tracks", "subtitles", "captions"})
    assert not quick.warnings


@pytest.mark.parametrize("can_open", [False, True])
def test_duplicate_dialog_actions_have_equal_size_and_translated_text(quick, qtbot, tmp_path, can_open):
    controller = quick.controller
    result = tmp_path / "video.mkv"
    result.write_bytes(b"fixture")
    existing = Task("https://example.test/video", state=State.COMPLETED if can_open else State.QUEUED, final_path=str(result) if can_open else "")
    controller.scheduler.tasks[existing.id] = existing
    controller._duplicate_id = existing.id
    dialog = quick.window.findChild(QObject, "duplicateDialog")
    for language in ("ru", "en", "be", "uk"):
        controller.settings.setValue("language", language)
        for theme in ("dark", "light"):
            controller.settings.setValue("theme", theme)
            controller.duplicateRequested.emit()
            qtbot.wait(50)
            buttons = [item(quick, name) for name in ("cancelDuplicate", "openDuplicate", "repeatDuplicate")]
            assert buttons[1].isVisible() == can_open
            visible = [button for button in buttons if button.isVisible()]
            assert all(button.height() == 40 for button in visible)
            assert max(button.width() for button in visible) - min(button.width() for button in visible) < 1
            for button in visible:
                assert button.width() >= button.property("implicitWidth")
                origin = button.mapToScene(QPointF())
                assert origin.x() >= dialog.property("x") + dialog.property("leftPadding") - 1
                assert origin.x() + button.width() <= dialog.property("x") + dialog.property("width") - dialog.property("rightPadding") + 1
            if language == "ru":
                assert dialog.property("title") == "Повторная загрузка"
                assert "Эта запись уже есть" in item(quick, "duplicateQuestion").property("text")
                assert "задание" not in item(quick, "duplicateQuestion").property("text")
            QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    assert not quick.warnings


@pytest.mark.parametrize("action", ["cancelDuplicate", "openDuplicate", "repeatDuplicate"])
def test_duplicate_dialog_keeps_cancel_open_and_repeat_actions(quick, qtbot, tmp_path, monkeypatch, action):
    controller = quick.controller
    path = tmp_path / "video.mkv"
    path.write_bytes(b"fixture")
    existing = Task("https://example.test/video", state=State.COMPLETED, final_path=str(path))
    controller.scheduler.tasks[existing.id] = existing
    controller._duplicate_id = existing.id
    pending = Task(existing.url)
    controller._pending = [pending]
    commits, opens = [], []
    monkeypatch.setattr(controller, "_commit", lambda tasks, folder: commits.append(tasks))
    monkeypatch.setattr(controller, "openResult", lambda *args: opens.append(args))
    controller.changed.emit()
    controller.duplicateRequested.emit()
    qtbot.wait(50)
    click(quick, action)
    qtbot.wait(30)
    assert not controller._pending
    assert bool(opens) == (action == "openDuplicate")
    assert bool(commits) == (action == "repeatDuplicate")
    if commits:
        assert commits[0] == [pending] and pending.repeat
    assert not quick.warnings


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
    configuration = item(quick, "configuration")
    preview = item(quick, "mediaPreview")
    workspace = item(quick, "workbench")
    gap = preview.mapToScene(QPointF()).x() - configuration.mapToScene(QPointF(configuration.width(), 0)).x()
    assert 400 <= configuration.width() <= 640
    assert 360 <= preview.width() <= 592
    assert gap >= 24
    if workspace.width() >= 1200:
        assert configuration.width() >= 599 and preview.width() >= 553
        assert 48 <= gap <= 64
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


@pytest.mark.parametrize("dimensions", [(1920, 1080), (800, 800), (720, 1280)])
def test_preview_keeps_16_9_bounds_and_original_media_proportions(quick, qtbot, dimensions):
    from PySide6.QtGui import QImage

    composer = quick.controller.composer
    prepared(composer)
    image = QImage(*dimensions, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkCyan)
    quick.controller.media._source = quick.preview.put(image)
    quick.controller.media.changed.emit()
    poster, preview = item(quick, "previewImage"), item(quick, "mediaPreview")
    qtbot.waitUntil(lambda: poster.property("paintedHeight") > 0)
    for width, height in ((1024, 700), (1536, 840)):
        quick.window.resize(width, height)
        for mode in ("video", "audio"):
            composer.setMode(mode)
            for title in ("Short title", "A longer video title that wraps naturally across the action panel " * 2):
                composer.task.title = title
                composer.changed.emit()
                qtbot.wait(60)
                assert abs(preview.width() / preview.height() - 16 / 9) < 0.001
                painted_width, painted_height = poster.property("paintedWidth"), poster.property("paintedHeight")
                assert abs(painted_width / painted_height - dimensions[0] / dimensions[1]) < 0.001
                assert painted_width <= preview.width() + 1 and painted_height <= preview.height() + 1
                assert min(abs(painted_width - preview.width()), abs(painted_height - preview.height())) < 1
                if dimensions == (1920, 1080):
                    assert abs(painted_width - preview.width()) < 1 and abs(painted_height - preview.height()) < 1
    assert not quick.warnings


@pytest.mark.parametrize("size", [(1024, 700), (1280, 800), (1920, 1080), (2560, 1440)])
def test_pages_share_content_bounds_with_header_and_download_rows(quick, qtbot, size):
    quick.window.resize(*size)
    prepared(quick.controller.composer)
    row = Task("https://example.test/layout", title="A queued download", state=State.DOWNLOADING)
    quick.controller.scheduler.tasks[row.id] = row
    quick.controller.scheduler.changed.emit(row)
    for page, content_name in (("downloads", "downloadsContent"), ("settings", "settingsContent"), ("about", "aboutContent")):
        quick.controller.navigate(page)
        qtbot.wait(50)
        content = item(quick, content_name)
        header = item(quick, "pageHeaderContent")
        heading = item(quick, "pageHeading")
        left = content.mapToScene(QPointF()).x()
        assert abs(left - heading.mapToScene(QPointF()).x()) < 1
        assert abs(content.width() - header.width()) < 1
        assert content.width() <= 1280
        assert left >= 20 and left + content.width() < size[0]
        if page == "downloads":
            assert item(quick, "sourceUrl").width() == content.width()
            download = item(quick, "downloadRowContent-" + row.id)
            assert download.width() == content.width()
            preview = item(quick, "mediaPreview")
            assert abs(preview.mapToScene(QPointF(preview.width(), 0)).x() - (left + content.width())) < 1
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


@pytest.mark.parametrize("playlist", [False, True])
def test_youtube_context_requires_explicit_choice_before_metadata(quick, qtbot, playlist):
    class Job(QObject):
        metadata_ready = Signal(str, dict)
        failed = Signal(str, str)
        finished = Signal(str)

        def __init__(self, task, tools, preferences, mode, parent):
            super().__init__(parent)
            self.task = task

        def start(self):
            pass

        def cancel(self):
            self.finished.emit(self.task.id)

    composer = quick.controller.composer
    composer.job_factory = Job
    composer.setUrl("https://www.youtube.com/watch?v=abc&list=PL123&index=2")
    composer.pasted()
    composer.analyze()  # Enter must not bypass the choice.
    qtbot.wait(50)
    assert composer.state["phase"] == "choice" and composer._job is None
    assert not composer.timer.isActive() and not composer.state["canDownload"]
    assert item(quick, "onlyVideo").isVisible() and item(quick, "choosePlaylist").isVisible()
    click(quick, "choosePlaylist" if playlist else "onlyVideo")
    assert composer._job.task.url == ("https://www.youtube.com/playlist?list=PL123" if playlist else "https://www.youtube.com/watch?v=abc")
    assert composer._job.task.playlist == playlist
    old = composer._job
    composer.setUrl("https://example.test/new")
    composer.timer.stop()
    old.metadata_ready.emit(old.task.id, INFO)
    assert composer.task is None and composer.state["phase"] == "loading"


@pytest.mark.parametrize("source", ["YoutubeTab", "SoundcloudSet"])
def test_playlist_format_selection_and_unavailable_rows(quick, qtbot, source, monkeypatch):
    composer = quick.controller.composer
    composer._url = "https://example.test/playlist"
    composer._ready(composer._generation, Task(composer._url), {
        "_type": "playlist", "title": "Test playlist", "extractor_key": source, "entries": [
            {"title": "One", "url": "https://example.test/one"},
            {"title": "Private", "url": "https://example.test/private", "availability": "private"},
            {"title": "Three", "url": "https://example.test/three"},
        ]})
    qtbot.wait(50)
    assert composer.state["isPlaylist"] and composer.state["audioAvailable"]
    assert composer.state["videoAvailable"] == (source == "YoutubeTab")
    composer.setMode("audio")
    composer.select("mp3:192")
    qtbot.wait(20)
    click(quick, "downloadButton")
    qtbot.wait(80)
    dialog = quick.window.findChild(QObject, "playlistDialog")
    assert dialog.property("opened")
    assert item(quick, "cancelPlaylist").height() == item(quick, "downloadPlaylist").height() == 40
    assert item(quick, "selectAllPlaylist").height() == item(quick, "selectNonePlaylist").height() == 40
    assert dialog.property("selectedIds").toVariant() == [1, 3]
    assert not item(quick, "playlistEntry2").isEnabled()
    assert "Недоступно" in item(quick, "playlistEntry2").property("text")
    monkeypatch.setattr(quick.controller.scheduler, "pump", lambda: None)
    click(quick, "downloadPlaylist")
    qtbot.wait(30)
    queued = list(quick.controller.scheduler.tasks.values())
    assert [t.playlist_index for t in queued] == [1, 3]
    assert all(t.selection == "mp3:192" and not t.playlist and not t.formats for t in queued)
    assert not dialog.property("opened")


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


@pytest.mark.parametrize("name", ["play", "retry", "youtube", "spinner", "trim", "settings", "captions", "folderOpen", "reddit", "soundcloud", "twitch", "link", "pinterest", "bandcamp",
                                  "about-media", "about-timeline", "about-range", "about-queue"])
def test_tinted_icons_render_including_svg_with_leading_license_comments(qapp, name):
    provider = IconProvider(Path(__file__).parents[1] / "src/al_media/quick/qml/icons")
    dimensions = QSize(144, 64) if name.startswith("about-") else QSize(32, 32)
    rendered = provider.requestImage(name + "/4f7ef8", QSize(), dimensions)
    assert any(rendered.pixelColor(x, y).alpha() > 100 for x in range(rendered.width()) for y in range(rendered.height())), name


@pytest.mark.parametrize("side", [24, 30, 36, 48])
def test_svg_provider_preserves_original_logo_proportions_at_each_scale(qapp, tmp_path, side):
    # A 2:1 mark must retain its aspect ratio when requested on a square canvas.
    # QML's PreserveAspectFit cannot undo distortion inside that canvas.
    (tmp_path / "wide.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><rect width="200" height="100" fill="currentColor"/></svg>', encoding="utf-8")
    provider = IconProvider(tmp_path)
    rendered = provider.requestImage("wide/4f7ef8", QSize(), QSize(side, side))
    assert rendered.width() == rendered.height() == side
    assert rendered.pixelColor(side // 2, side // 2).alpha() == 255
    assert rendered.pixelColor(side // 2, 1).alpha() == 0
    assert rendered.pixelColor(side // 2, side - 2).alpha() == 0
    occupied = [y for y in range(side) if rendered.pixelColor(side // 2, y).alpha() > 100]
    assert abs(len(occupied) - side / 2) <= 1


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


@pytest.mark.parametrize("size", [(1024, 640), (1280, 720), (1536, 793)])
@pytest.mark.parametrize("language", ["ru", "en", "be", "uk"])
def test_source_messages_keep_heading_and_help_aligned_across_states(quick, qtbot, size, language):
    quick.window.resize(*size)
    quick.controller.settings.setValue("language", language)
    composer = quick.controller.composer
    qtbot.wait(60)
    scroll = item(quick, "downloadsScroll")
    heading, help_text = item(quick, "composerHeading"), item(quick, "composerHelp")
    initial = [obj.mapToScene(QPointF()) for obj in (heading, help_text)]
    viewport = scroll.mapToScene(QPointF())
    assert abs(initial[0].y() + heading.height() / 2 - (viewport.y() + scroll.height() / 2)) < 24

    for history in (False, True):
        if history:
            task = Task("https://example.test/saved", title="Saved download", state=State.INTERRUPTED)
            quick.controller.scheduler.tasks[task.id] = task
            quick.controller.scheduler.changed.emit(task)
        for source, phase in (("", "empty"), ("https://example.test/video", "loading"),
                              ("https://www.youtube.com/watch?v=abc&list=PL123", "choice"),
                              ("https://example.test/a\nhttps://example.test/b", "batch"),
                              ("https://example.test/error", "error")):
            composer.setUrl(source)
            composer.timer.stop()
            if phase == "error":
                composer._fail("error_unavailable")
            qtbot.wait(30)
            assert composer.state["phase"] == phase
            for obj, original in zip((heading, help_text), initial, strict=True):
                position = obj.mapToScene(QPointF())
                assert abs(position.y() - original.y()) < 1
                assert abs(position.x() + obj.width() / 2 - (viewport.x() + scroll.width() / 2)) < 1
            assert heading.property("implicitWidth") <= heading.width()
            if phase == "loading":
                spinner = item(quick, "analysisSpinner")
                top = spinner.mapToScene(QPointF()).y()
                assert top >= item(quick, "sourceUrl").mapToScene(QPointF()).y() + item(quick, "sourceUrl").height()
                assert top + spinner.height() < initial[0].y()
            if phase in {"choice", "batch"} and history:
                action = item(quick, "onlyVideo" if phase == "choice" else "downloadBatch")
                assert action.mapToScene(QPointF()).y() + action.height() < item(quick, "queueHeading").mapToScene(QPointF()).y()
        prepared(composer)
        qtbot.wait(40)
        composer.setUrl("")
        qtbot.wait(40)
        assert abs(heading.mapToScene(QPointF()).y() - initial[0].y()) < 1
    assert not quick.warnings


@pytest.mark.parametrize("size", [(1024, 700), (1280, 720), (1536, 793)])
def test_queue_position_survives_source_analysis_and_clearing(quick, qtbot, size):
    quick.window.resize(*size)
    composer = quick.controller.composer
    history = Task("https://example.test/history", title="Saved download", state=State.COMPLETED)
    quick.controller.scheduler.tasks[history.id] = history
    quick.controller.scheduler.changed.emit(history)
    qtbot.wait(60)

    def heading_y():
        return item(quick, "queueHeading").mapToScene(QPointF()).y()

    initial = heading_y()
    initial_height = item(quick, "workbench").height()
    for url, phase in (("https://example.test/video", "loading"),
                       ("https://www.youtube.com/watch?v=abc&list=PL123", "choice"),
                       ("https://example.test/a\nhttps://example.test/b", "batch"), ("", "empty")):
        composer.setUrl(url)
        composer.timer.stop()
        qtbot.wait(40)
        assert composer.state["phase"] == phase
        assert abs(heading_y() - initial) < 1
    prepared(composer)
    qtbot.wait(60)
    assert abs(heading_y() - initial) < 1
    composer.setMode("audio")
    composer.toggleRange()
    qtbot.wait(40)
    assert abs(heading_y() - initial) < 1
    composer.setUrl("")
    qtbot.wait(40)
    assert abs(heading_y() - initial) < 1
    composer.setUrl("https://example.test/error")
    composer.timer.stop()
    composer._fail("error_unavailable")
    qtbot.wait(40)
    assert abs(heading_y() - initial) < 1
    composer._ready(composer._generation, Task("https://example.test/playlist"), {
        "_type": "playlist", "title": "Playlist", "extractor_key": "YoutubeTab", "entries": [
            {"title": "One", "url": "https://example.test/one"},
        ]})
    qtbot.wait(60)
    assert composer.state["isPlaylist"] and abs(heading_y() - initial) < 1
    composer.setUrl("")
    qtbot.wait(40)
    assert abs(heading_y() - initial) < 1
    info = deepcopy(INFO)
    info["title"] = "A longer video title with more details " * 5
    composer._ready(composer._generation, Task("https://example.test/long"), info)
    qtbot.wait(60)
    expanded = heading_y()
    expanded_height = item(quick, "workbench").height()
    assert expanded_height > initial_height
    composer.setUrl("")
    qtbot.wait(40)
    assert item(quick, "workbench").height() == expanded_height
    assert abs(heading_y() - expanded) < 1
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
            assert content.height() == 144
            for index in range(3):
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
    quick.controller.preferences.folder = str(folders[0])
    quick.controller.settings.resetFolder()
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
    qtbot.waitUntil(lambda: Path(quick.controller.preferences.folder) == folders[1])
    assert not quick.warnings


def test_settings_has_no_back_to_downloads_link(quick, qtbot):
    quick.controller.navigate("settings")
    qtbot.wait(30)
    assert not any("Назад к загрузкам" in str(obj.property("text") or "") for obj in item(quick, "settingsPage").findChildren(QQuickItem))


@pytest.mark.parametrize("keyboard", [False, True])
def test_recent_dropdown_does_not_apply_draft_when_opened(quick, qtbot, tmp_path, keyboard):
    other = tmp_path / "Existing"
    other.mkdir()
    settings = quick.controller.settings
    settings.preferences.folder = str(tmp_path)
    settings.preferences.recent_folders = [str(tmp_path), str(other)]
    settings.resetFolder()
    quick.controller.changeFolder()
    qtbot.wait(60)
    field = item(quick, "downloadFolder")
    trigger = item(quick, "recentFolders")
    assert trigger.parentItem() == field and not trigger.property("text")
    draft = tmp_path / "Uncommitted"
    settings.editFolder(str(draft))
    field.forceActiveFocus()
    if keyboard:
        QTest.keyClick(quick.window, Qt.Key.Key_Down)
    else:
        click(quick, "recentFolders")
    menu = trigger.findChild(QObject, "recentFoldersMenu")
    qtbot.waitUntil(lambda: menu.property("opened"))
    qtbot.wait(450)
    assert settings.preferences.folder == str(tmp_path) and not draft.exists()
    assert item(quick, "folderError").property("text") == text(settings.preferences.language, "folder_missing")
    if keyboard:
        QTest.keyClick(quick.window, Qt.Key.Key_Down)
        QTest.keyClick(quick.window, Qt.Key.Key_Return)
    else:
        click(quick, "recentFolder-1")
    qtbot.waitUntil(lambda: settings.preferences.folder == str(other) and not settings.busy)
    assert not menu.property("visible") and not draft.exists()
    assert item(quick, "folderError").property("text") == ""
    assert not item(quick, "folderFeedback").isVisible()
    assert not quick.warnings


@pytest.mark.parametrize("language", ["ru", "en", "be", "uk"])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_about_features_fit_and_relocated_licenses_open_in_every_language(quick, qtbot, language, theme):
    quick.controller.settings.setValue("language", language)
    quick.controller.settings.setValue("theme", theme)
    quick.controller.navigate("about")
    for width, height in ((1024, 720), (1280, 720), (1280, 760), (1536, 792), (1536, 840), (1920, 1080)):
        quick.window.resize(width, height)
        qtbot.wait(50)
        grid = item(quick, "aboutFeatures")
        for key in ("media", "fragments", "queue", "files"):
            feature = item(quick, "aboutFeature-" + key)
            point = feature.mapToScene(QPointF())
            assert point.x() >= 0 and point.x() + feature.width() <= width
            assert feature.height() > 30 and feature.width() <= grid.width()
            illustration = item(quick, feature.objectName() + "Illustration")
            for suffix in ("Title", "Description"):
                label = item(quick, feature.objectName() + suffix)
                assert label.property("text") and not label.property("text").startswith("about_")
                assert label.property("paintedWidth") <= label.width() + 1
                assert label.mapToScene(QPointF()).x() + label.width() + 23 <= illustration.mapToScene(QPointF()).x()
                assert label.mapToScene(QPointF(0, label.height())).y() <= point.y() + feature.height()
        link = item(quick, "allSourcesButtonText")
        sources = item(quick, "sourcesGrid")
        assert abs(sources.width() - item(quick, "aboutSources").width()) < 1
        assert abs(link.mapToScene(QPointF()).x() - sources.mapToScene(QPointF()).x()) < 1
        assert not quick.window.findChild(QQuickItem, "sourcesAvailability")
        version = item(quick, "aboutVersion")
        licenses = item(quick, "licensesButtonText")
        assert version.property("font").pixelSize() == licenses.property("font").pixelSize() == 12
        assert abs(version.mapToScene(QPointF()).y() - licenses.mapToScene(QPointF()).y()) < 1
        names = ("youtube", "facebook", "instagram", "twitch", "pinterest", "tiktok", "soundcloud", "x-twitter", "reddit", "bandcamp")
        cells = [item(quick, "source-" + name) for name in names]
        assert max(cell.width() for cell in cells) - min(cell.width() for cell in cells) <= 1  # Whole-pixel rounding.
        columns = sources.property("columns")
        for i, cell in enumerate(cells):
            assert abs(cell.x() - cells[i % columns].x()) < 1
        assert abs(cells[0].x()) < 1
        assert abs(cells[columns - 1].x() + cells[columns - 1].width() - sources.width()) < 1
        assert grid.mapToScene(QPointF(0, grid.height())).y() < sources.mapToScene(QPointF()).y()
        assert item(quick, "aboutDeveloper").mapToScene(QPointF()).y() > link.mapToScene(QPointF(0, link.height())).y()
        if width >= 1280 and height >= 760:
            scroll = item(quick, "aboutScroll")
            assert scroll.property("contentHeight") <= scroll.height() + 1, "The full About page should fit a maximized Full HD window"
            bar = item(quick, "aboutScrollBar")
            assert bar.property("size") >= 1
            assert bar.findChild(QQuickItem, "scrollThumb").property("opacity") == 0
    quick.window.resize(1280, 720)
    qtbot.wait(50)
    click(quick, "licensesButton")
    dialog = quick.window.findChild(QObject, "licensesDialog")
    qtbot.waitUntil(lambda: dialog.property("opened"))
    assert len(quick.controller.licenseSections) == 6
    assert "Lucide" in quick.controller.noticesText and "Font Awesome" in quick.controller.noticesText
    QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    assert not quick.warnings


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


def test_audio_track_change_filters_formats_and_audio_mode_does_not_create_subtitle_sidecars(scheduler):
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
    assert task.subtitle_mode == "none" and task.subtitle_language == ""


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


def test_unknown_size_keeps_container_without_empty_separator(quick, qtbot):
    composer = quick.controller.composer
    task = prepared(composer)
    task.duration = None
    for stream in task.formats:
        stream.pop("filesize", None)
    composer.changed.emit()
    qtbot.wait(40)
    assert composer.state["estimated"] == ""
    assert item(quick, "outputSummary").property("text") == "MKV"
    task.formats[0]["filesize"] = 1_000_000
    task.formats[2]["filesize"] = 200_000
    composer.changed.emit()
    qtbot.wait(40)
    assert item(quick, "outputSummary").property("text") == "MKV · ≈ 1.2 МБ"


def test_manual_folder_commits_on_enter_and_escape_restores_saved_path(quick, qtbot, tmp_path):
    quick.controller.changeFolder()
    qtbot.wait(60)
    settings = quick.controller.settings
    original = settings.preferences.folder
    field = item(quick, "downloadFolder")
    destination = str(tmp_path / "Выбранная папка")
    Path(destination).mkdir()
    field.forceActiveFocus()
    QTest.keyClick(quick.window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    from PySide6.QtGui import QInputMethodEvent
    from PySide6.QtWidgets import QApplication

    paste = QInputMethodEvent()
    paste.setCommitString(destination)
    QApplication.sendEvent(quick.window, paste)
    assert settings.state["folderDraft"] == destination and settings.preferences.folder == original
    assert Path(destination).is_dir()
    QTest.keyClick(quick.window, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: settings.preferences.folder == destination and not field.hasActiveFocus())
    assert Path(destination).is_dir()
    assert settings.state["folderStatus"] == "saved"
    field.forceActiveFocus()
    settings.editFolder(str(tmp_path / "Отменено"))
    QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    assert settings.state["folderDraft"] == destination
    assert not (tmp_path / "Отменено").exists()
    assert quick.controller.page == "settings"
    assert not quick.warnings


def test_manual_folder_invalid_or_unwritable_preserves_saved_destination(scheduler, tmp_path, qtbot):
    settings = SettingsViewModel(scheduler.preferences, persist=False)
    original = settings.preferences.folder
    for value in ("", "relative/path"):
        settings.editFolder(value)
        settings.applyFolder()
        qtbot.waitUntil(lambda: not settings.busy)
        assert settings.state["folderError"] == "folder_invalid"
        assert settings.preferences.folder == original
    occupied = tmp_path / "file.txt"
    occupied.write_text("keep", encoding="utf-8")
    settings.editFolder(str(occupied))
    settings.applyFolder()
    qtbot.waitUntil(lambda: not settings.busy)
    assert settings.state["folderError"] == "folder_not_directory"
    assert settings.preferences.folder == original and occupied.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("missing", [False, True])
def test_invalid_folder_keeps_editing_focus_until_escape(quick, qtbot, tmp_path, missing):
    quick.controller.changeFolder()
    qtbot.wait(40)
    settings = quick.controller.settings
    field = item(quick, "downloadFolder")
    original = settings.preferences.folder
    value = str(tmp_path / "Typo") if missing else "relative/path"
    settings.editFolder(value)
    QTest.keyClick(quick.window, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: settings.state["folderError"] == ("folder_missing" if missing else "folder_invalid"))
    assert field.hasActiveFocus() and settings.preferences.folder == original
    QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    assert not field.hasActiveFocus() and settings.state["folderDraft"] == original
    assert not quick.warnings


def test_filename_preview_has_consistent_spacing_and_fits_all_languages(quick, qtbot):
    controller = quick.controller
    controller.navigate("settings")
    controller.settings.setValue("name_style", "artist_title")
    controller.settings.setValue("subfolders", "playlist")
    for language in ("ru", "en", "be", "uk"):
        controller.settings.setValue("language", language)
        quick.window.resize(1024, 720)
        qtbot.wait(40)
        combo = item(quick, "subfolders")
        preview = item(quick, "filenamePreview")
        panel = preview.parentItem()
        heading = item(quick, "audioSettingsHeading")
        assert panel.mapToScene(QPointF()).y() - combo.mapToScene(QPointF(0, combo.height())).y() >= 16
        assert heading.mapToScene(QPointF()).y() - panel.mapToScene(QPointF(0, panel.height())).y() >= 32
        assert preview.height() <= panel.height() - 16
        assert abs(panel.mapToScene(QPointF()).x() - combo.mapToScene(QPointF()).x()) < 1
    assert not quick.warnings


def test_completed_file_removal_and_restore_update_row_without_changing_history(quick, qtbot, tmp_path):
    result = tmp_path / "result.mkv"
    result.write_bytes(b"fixture")
    task = Task("https://example.test/video", title="File", state=State.COMPLETED, final_path=str(result))
    controller = quick.controller
    controller.scheduler.tasks[task.id] = task
    controller.scheduler.changed.emit(task)
    qtbot.wait(40)
    assert controller.downloads._rows[task.id]["canOpen"]
    result.unlink()
    qtbot.waitUntil(lambda: controller.downloads._rows[task.id]["status"] == "Файл не найден", timeout=3000)
    assert not controller.downloads._rows[task.id]["canOpen"]
    assert not item(quick, "openResult-" + task.id).isVisible()
    result.write_bytes(b"restored")
    qtbot.waitUntil(lambda: controller.downloads._rows[task.id]["canOpen"], timeout=3000)
    assert controller.downloads._rows[task.id]["status"] == "Готово" and task.state == State.COMPLETED
    assert not quick.warnings


def test_subtitle_dialog_uses_localized_languages_and_embeds_video_only(quick, qtbot):
    composer = quick.controller.composer
    task = prepared(composer)
    task.subtitles = {"ru": [{"ext": "vtt"}], "en": [{"ext": "vtt"}]}
    task.automatic_captions = {"ru": [{"ext": "vtt"}], "en-orig": [{"ext": "vtt"}], "ja": [{"ext": "vtt"}], "xx": [{"ext": "vtt"}]}
    composer.changed.emit()
    assert [row["label"] for row in composer.state["subtitles"]][1:] == ["Русский", "Английский", "Японский · автоматические"]
    assert composer.state["tracks"][0]["label"] == "По умолчанию"
    click(quick, "tracksButton")
    composer.setExtra("subtitle", "0:ru")
    qtbot.wait(40)
    assert task.subtitle_mode == "embedded" and item(quick, "subtitleStorageHint").isVisible()
    QTest.keyClick(quick.window, Qt.Key.Key_Escape)
    composer.setMode("audio")
    assert task.subtitle_mode == "none" and not task.subtitle_language
    assert not composer.state["hasExtra"]
    assert not quick.warnings
