"""Render native documentation screenshots with a local fixture and no network."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from al_media.config import Preferences, app_root
from al_media.core.scheduler import Scheduler
from al_media.database import Database
from al_media.models import State, Task
from al_media.ui.main_window import MainWindow


def main():
    app = QApplication([])
    for name in ("segoeui.ttf", "seguisb.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
    app.setFont(QFont("Segoe UI", 10))
    Preferences.save = lambda self: None
    root = app_root()
    temporary = root / ".tmp" / "documentation-fixture"
    temporary.mkdir(parents=True, exist_ok=True)
    output = root / "docs" / "images"
    output.mkdir(exist_ok=True)
    db = Database(Path(":memory:"))
    preferences = Preferences(folder=str(temporary / "downloads"))
    scheduler = Scheduler(db, {}, preferences)
    window = MainWindow(scheduler, preferences, probe_tools=False)
    window.settings_loading = True
    window.path_edit.setText("D:/Downloads")
    window.resize(1280, 800)
    window.show()
    QTest.qWait(50)
    window.grab().save(str(output / "downloads-empty.png"))
    window.input.blockSignals(True)
    window.input.setText("https://www.youtube.com/watch?v=example")
    window.input.blockSignals(False)
    window._composer_state("loading")
    QTest.qWait(50)
    window.grab().save(str(output / "downloads-loading.png"))
    art = QPixmap(1280, 720)
    painter = QPainter(art)
    gradient = QLinearGradient(0, 0, 1280, 720)
    gradient.setColorAt(0, QColor("#294358"))
    gradient.setColorAt(1, QColor("#b77d76"))
    painter.fillRect(art.rect(), gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#ead0b5"))
    painter.drawEllipse(1010, 115, 105, 105)
    for index, height in enumerate((280, 410, 320, 250, 370, 285, 430, 310, 260, 360, 290, 400)):
        x, y = index * 112, 720 - height
        painter.fillRect(x, y, 100, height, QColor("#1c303d"))
        for a in range(x + 16, x + 90, 24):
            for b in range(y + 20, 700, 35):
                painter.fillRect(a, b, 7, 12, QColor("#d6ad82"))
    painter.setPen(QColor("#fff4df"))
    painter.setFont(QFont("Segoe UI", 46, QFont.Weight.DemiBold))
    painter.drawText(48, 100, "CITY AFTER DARK")
    painter.setFont(QFont("Segoe UI", 18))
    painter.drawText(50, 146, "EVENING WALKS")
    painter.end()
    cover = "https://example.test/local-cover.jpg"
    window.images.cache[cover] = art
    formats = [{"format_id": str(height), "height": height, "vcodec": "h264", "acodec": "none", "filesize": height * 90000} for height in (2160, 1440, 1080, 720, 480)]
    formats.append({"format_id": "audio", "vcodec": "none", "acodec": "aac", "ext": "m4a", "abr": 192, "filesize": 20000000})
    source = Task("https://www.youtube.com/watch?v=example", title="Вечерний город — прогулка по набережной", author="City Walks", source="YouTube",
                  duration=1122, thumbnail=cover, formats=formats, state=State.READY)
    window.input.blockSignals(True)
    window.input.setText(source.url)
    window.input.blockSignals(False)
    window.preview_task = source
    window._render_preview()
    QTest.qWait(220)
    window.grab().save(str(output / "downloads-ready.png"))
    path = temporary / "Ночной маршрут.mp3"
    with path.open("wb") as file:
        file.truncate(43 * 1048576)
    fixtures = [
        Task("https://example.test/complete", title="Ночной маршрут", source="SoundCloud", state=State.COMPLETED, selection="mp3:320", output_bitrate=320000, final_path=str(path), thumbnail=cover),
        Task("https://example.test/current", title="Дорога через горы", source="YouTube", state=State.DOWNLOADING, selection="video:1440", percent=58, speed=4.2 * 1048576, eta=37, total=342 * 1048576),
        Task("https://example.test/waiting", title="Рассвет над морем", source="YouTube", state=State.QUEUED, selection="video:2160", total=210 * 1048576),
    ]
    for task in fixtures:
        scheduler.tasks[task.id] = task
        window._task_changed(task)
    app.processEvents()
    QTest.qWait(220)
    window.grab().save(str(output / "downloads.png"))
    window.preview_advanced.setChecked(True)
    QTest.qWait(50)
    window.options_popup.grab().save(str(output / "download-options-video.png"))
    window.preview_advanced.setChecked(False)
    window.format_picker.audio.click()
    QTest.qWait(220)
    window.grab().save(str(output / "downloads-preview.png"))
    window.preview_advanced.setChecked(True)
    QTest.qWait(50)
    window.options_popup.grab().save(str(output / "download-options-audio.png"))
    window.preview_advanced.setChecked(False)
    portrait = QPixmap(360, 640)
    portrait.fill(QColor("#6a8caa"))
    painter = QPainter(portrait)
    painter.fillRect(180, 0, 180, 640, QColor("#c5a07b"))
    painter.fillRect(80, 220, 200, 420, QColor("#243a4a"))
    painter.end()
    window.media_preview.current = portrait
    window.media_preview.cover = portrait
    window.media_preview.update()
    QTest.qWait(50)
    window.grab().save(str(output / "downloads-portrait.png"))
    for theme in ("dark", "light"):
        preferences.theme = theme
        window.theme.setCurrentIndex(window.theme.findData(theme))
        window._apply_appearance()
        for page, filename in ((1, "settings-light.png" if theme == "light" else "settings-dark.png"), (2, "about.png" if theme == "dark" else "")):
            if filename:
                window._navigate(page)
                QTest.qWait(50)
                window.grab().save(str(output / filename))
    window.explicit_exit = True
    window.close()
    db.close()
    print(output)


if __name__ == "__main__":
    main()
