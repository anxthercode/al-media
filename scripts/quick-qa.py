"""Capture the actual Qt Quick client area with isolated, deterministic fixtures.

No network requests, user settings, profile lock or real download directory.
Use QT_SCALE_FACTOR for an additional process at a different logical scale.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PySide6.QtCore import QMetaObject, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from al_media.config import Preferences
from al_media.core.scheduler import Scheduler
from al_media.database import Database
from al_media.models import State, Task
from al_media.quick.bootstrap import QuickApplication


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("build/qa/quick"))
    parser.add_argument("--matrix", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    font = QFont("Segoe UI")
    font.setPixelSize(14)
    app.setFont(font)
    prefs = Preferences(folder="D:\\Media", recent_folders=["D:\\Media", "D:\\Downloads"])
    db = Database(Path(":memory:"))
    scheduler = Scheduler(db, {}, prefs)
    presentation = QuickApplication(app, scheduler, prefs, isolated=True)
    root, controller = presentation.window, presentation.controller
    composer = controller.composer
    root.resize(1280, 720)
    root.show()
    QTest.qWait(250)
    assert root.grabWindow().save(str(args.output / "empty.png"))
    composer._phase = "loading"
    composer.changed.emit()
    QTest.qWait(220)
    loading_frame = root.grabWindow()
    assert loading_frame.save(str(args.output / "loading.png"))
    spinner = root.findChild(QQuickItem, "analysisSpinner")
    assert spinner is not None
    origin = spinner.mapToScene(QPointF())
    ratio = loading_frame.width() / root.width()
    spinner_rect = (round(origin.x() * ratio), round(origin.y() * ratio), round(spinner.width() * ratio), round(spinner.height() * ratio))
    QTest.qWait(150)
    next_frame = root.grabWindow()
    assert loading_frame.copy(*spinner_rect) != next_frame.copy(*spinner_rect), "Spinner rendered identical frames"
    composer._url = "https://youtu.be/qOzDWaaWBnI"
    composer._generation += 1
    composer._ready(
        composer._generation,
        Task(composer._url),
        {
            "title": "А ты её достоин? — Lada Priora",
            "extractor_key": "YouTube",
            "uploader": "ОколоОфициалы",
            "duration": 2077,
            "formats": [
                {"format_id": "v1", "vcodec": "vp9", "acodec": "none", "height": 2160, "filesize": 4_500_000_000},
                {"format_id": "v2", "vcodec": "avc1", "acodec": "none", "height": 1080, "filesize": 800_000_000},
                {"format_id": "a1", "vcodec": "none", "acodec": "opus", "ext": "webm", "filesize": 200_000_000},
            ],
        },
    )
    # Generate a local test pattern; QA must not depend on archived mockups.
    image = QImage(1280, 720, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 1280, 720)
    gradient.setColorAt(0, QColor("#22334b"))
    gradient.setColorAt(1, QColor("#548e9b"))
    painter.fillRect(image.rect(), gradient)
    painter.setPen(QColor("white"))
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "AL Media · Native UI QA")
    painter.end()
    controller.media._source = presentation.preview.put(image)
    controller.media.changed.emit()
    running = Task(composer._url, title=composer.task.title, state=State.DOWNLOADING, source="YouTube", selection="video:1080", percent=43, speed=5_300_000, eta=140)
    scheduler.tasks[running.id] = running
    scheduler.changed.emit(running)
    results = []
    sizes = [(1280, 720), (1280, 800), (1536, 864), (1920, 1080), (1024, 700)] if args.matrix else [(1280, 720)]

    def item(name):
        found = root.findChild(QQuickItem, name)
        if found is None:
            pending = [root.contentItem()]
            while pending:
                candidate = pending.pop()
                if candidate.objectName() == name:
                    found = candidate
                    break
                pending.extend(candidate.childItems())
        assert found is not None, name
        return found

    for width, height in sizes:
        root.resize(width, height)
        for page in ("downloads", "settings", "about"):
            controller.navigate(page)
            QTest.qWait(220)
            suffix = f"{page}-{width}x{height}"
            captured = root.grabWindow()
            assert not captured.isNull(), "Native render did not produce an image"
            assert captured.save(str(args.output / (suffix + ".png")))
            for name in {"downloads": ["configuration", "mediaPreview", "downloadButton"], "settings": ["concurrencyField", "downloadFolder"], "about": ["licensesButton", "navAbout"]}[page]:
                obj = item(name)
                origin = obj.mapToScene(QPointF())
                results.append(
                    {"viewport": [width, height], "page": page, "item": name, "x": round(origin.x(), 2), "y": round(origin.y(), 2), "width": round(obj.width(), 2), "height": round(obj.height(), 2), "dpr": root.devicePixelRatio()}
                )
                assert origin.x() >= -1 and origin.x() + obj.width() <= width + 1, (name, origin.x(), obj.width())
        # License dialog, native rendering and keyboard close.
        QMetaObject.invokeMethod(root, "showLicenses")
        QTest.qWait(150)
        root.grabWindow().save(str(args.output / f"licenses-{width}x{height}.png"))
        section = item("mainLicenseSection")
        section.setProperty("expanded", False)
        QTest.qWait(220)
        assert section.height() == 45
        root.grabWindow().save(str(args.output / f"licenses-collapsed-{width}x{height}.png"))
        section.setProperty("expanded", True)
        QTest.qWait(220)
        QTest.keyClick(root, Qt.Key.Key_Escape)
    controller.navigate("downloads")
    composer.toggleRange()
    composer.editRange("clip", True)
    composer.editRange("start", "1:")
    controller.navigate("settings")
    controller.back()
    assert composer.state["rangeStart"] == "1:" and not composer.state["canDownload"]
    composer.toggleRange()
    composer.editRange("start", "00:01:23")
    QTest.qWait(120)
    root.grabWindow().save(str(args.output / "range-draft.png"))
    composer.resetRange()
    composer.setMode("audio")
    QTest.qWait(180)
    root.grabWindow().save(str(args.output / "audio.png"))
    QMetaObject.invokeMethod(item("qualityPicker"), "openMenu")
    QTest.qWait(50)
    from PySide6.QtQml import QQmlProperty

    menu = QQmlProperty.read(item("qualityPicker"), "popup")
    popup_content = menu.property("contentItem")
    popup_origin = popup_content.mapToScene(QPointF())
    assert popup_origin.x() >= 0 and popup_origin.y() >= 0
    assert popup_origin.x() + popup_content.width() <= root.width()
    assert popup_origin.y() + popup_content.height() <= root.height()
    root.grabWindow().save(str(args.output / "bitrate-popup.png"))
    QTest.keyClick(root, Qt.Key.Key_Escape)
    controller.settings.setValue("theme", "light")
    controller.settings.setValue("language", "en")
    controller.navigate("settings")
    QTest.qWait(180)
    root.grabWindow().save(str(args.output / "settings-light-en.png"))
    controller.settings.setValue("theme", "dark")
    controller.settings.setValue("language", "ru")
    for path in ("about", "settings", "downloads"):
        controller.navigate(path)
        QTest.qWait(30)
    completed = Task(composer._url, title="Готовое видео", state=State.COMPLETED, source="YouTube", selection="video:1080", final_path="D:/Media/Готовое видео.mp4", final_size=5_000_000)
    scheduler.tasks[completed.id] = completed
    scheduler.changed.emit(completed)
    for width, height in sizes:
        root.resize(width, height)
        QTest.qWait(150)
        QMetaObject.invokeMethod(item("downloadsScroll"), "positionViewAtEnd")
        QTest.qWait(100)
        button = item("openResult-" + completed.id)
        QTest.mouseMove(root, button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint())
        QTest.qWait(180)
        root.grabWindow().save(str(args.output / f"completed-hover-{width}x{height}.png"))
        for name in ("openResult-", "showFolder-", "removeTask-"):
            action = item(name + completed.id)
            point = action.mapToScene(QPointF())
            assert 0 <= point.x() and point.x() + action.width() <= root.width(), name
    report = {"platform": app.platformName(), "geometry": results, "qmlWarnings": presentation.warnings}
    (args.output / "geometry.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assert not presentation.warnings, "QML emitted runtime warnings; inspect geometry.json"
    controller.quit()
    QTest.qWait(100)
    root.hide()
    presentation.dispose()
    app.processEvents()
    db.close()
    print(f"Qt Quick QA passed: {len(sizes)} client sizes, captures in {args.output.resolve()}")


if __name__ == "__main__":
    main()
