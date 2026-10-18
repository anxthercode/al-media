from PySide6.QtGui import QColor, QIcon, QPixmap

from al_media.config import Preferences
from al_media.models import Task
from al_media.ui.media_preview import MediaPreview, storyboard_frames
from al_media.ui.preview_frames import preview_source


def test_storyboard_selects_real_frames_across_sheets():
    task = Task("https://example.test/video", duration=20, formats=[{
        "protocol": "mhtml", "width": 160, "height": 90, "rows": 2, "columns": 2,
        "fps": .4, "fragments": [{"url": "https://example.test/one.jpg"}, {"url": "https://example.test/two.jpg"}]}])
    frames = storyboard_frames(task)
    assert len(frames) == 8
    assert [frame.url for frame in frames].count("https://example.test/one.jpg") == 4
    assert frames[0].rect == (0, 0, 160, 90)
    assert frames[3].rect == (160, 90, 160, 90)
    assert not storyboard_frames(Task(task.url))


def test_slideshow_three_second_interval_and_stale_image_guard(qtbot):
    class Cache:
        callbacks = []

        def fetch(self, url, callback, low_priority=False):
            self.callbacks.append((url, callback))

    cache = Cache()
    preview = MediaPreview(cache, Preferences(), QIcon())
    qtbot.addWidget(preview)
    preview.resize(320, 180)
    preview.show()
    first = Task("https://example.test/first", thumbnail="https://example.test/old.jpg")
    second = Task("https://example.test/second", thumbnail="https://example.test/new.jpg")
    preview.set_task(first)
    preview.set_task(second)
    red, blue = QPixmap(160, 90), QPixmap(160, 90)
    red.fill(QColor("red"))
    blue.fill(QColor("blue"))
    cache.callbacks[0][1](red)
    assert preview.current.isNull()
    cache.callbacks[1][1](blue)
    assert preview.current.toImage().pixelColor(0, 0) == QColor("blue")
    preview.frames = {0: red, 1: blue}
    preview.sync_animation()
    assert preview.timer.isActive() and preview.timer.interval() == 3000
    preview.advance()
    assert preview.animation.duration() == 300
    assert preview.index >= 0 and preview.fade < 1.0
    qtbot.waitUntil(lambda: preview.fade == 1.0, timeout=2000)
    preview.hide()
    assert not preview.timer.isActive() and preview.animation.state() == preview.animation.State.Stopped


def test_large_preview_retains_cover_instead_of_tiny_storyboards(qtbot):
    class Cache:
        def __init__(self):
            self.requests = []

        def fetch(self, url, callback, low_priority=False):
            self.requests.append((url, callback))

    cache = Cache()
    preview = MediaPreview(cache, Preferences(), QIcon())
    qtbot.addWidget(preview)
    preview.set_task(Task("https://example.test/video", thumbnail="https://example.test/cover.jpg", formats=[{
        "protocol": "mhtml", "width": 160, "height": 90, "rows": 2, "columns": 4,
        "fragments": [{"url": "https://example.test/tiny.jpg"}]}]))
    assert [url for url, _ in cache.requests] == ["https://example.test/cover.jpg"]
    image = QPixmap(1280, 720)
    image.fill(QColor("blue"))
    cache.requests[0][1](image)
    assert preview.current.size() == image.size() and not preview.frames


def test_preview_uses_modest_direct_stream_and_seekable_local_video(tmp_path):
    task = Task("https://example.test/video", duration=100, clip_start=10, clip_end=50, formats=[
        {"url": "https://example.test/4k.mp4", "vcodec": "av1", "height": 2160},
        {"url": "https://example.test/720.mp4", "vcodec": "avc1", "height": 720,
         "http_headers": {"Referer": "https://example.test/", "bad\nkey": "value", "Range": "bytes=0-", "X-Bad": "a\r\nb"}},
        {"url": "https://example.test/live.m3u8", "vcodec": "avc1", "height": 720, "protocol": "m3u8_native"},
        {"url": "https://example.test/drm.mp4", "vcodec": "avc1", "height": 720, "has_drm": True}])
    url, headers, start, duration = preview_source(task)
    assert url.endswith("/720.mp4") and headers == {"Referer": "https://example.test/"}
    assert (start, duration) == (10, 40)
    path = tmp_path / "clipped.mp4"
    path.write_bytes(b"fixture")
    task.final_path = str(path)
    assert preview_source(task) == (str(path.resolve()), {}, 0, 40)
    task.playlist = True
    assert preview_source(task) is None


def test_best_metadata_cover_and_fallback_candidates():
    from al_media.core.metadata import populate_task

    task = Task("https://example.test/video")
    populate_task(task, {"thumbnail": "https://example.test/small.jpg", "thumbnails": [
        {"url": "https://example.test/small.jpg", "width": 320, "height": 180},
        {"url": "https://example.test/large.jpg", "width": 1920, "height": 1080},
        {"url": "https://example.test/medium.jpg", "width": 1280, "height": 720}]})
    assert task.thumbnail.endswith("/large.jpg")
    assert task.thumbnail_candidates == ["https://example.test/large.jpg", "https://example.test/small.jpg", "https://example.test/medium.jpg"]


def test_portrait_preview_fills_sides_and_keeps_cover_during_mode_switch(qtbot):
    class Cache:
        def fetch(self, url, callback, low_priority=False):
            image = QPixmap(90, 160)
            image.fill(QColor("red"))
            callback(image)

    preview = MediaPreview(Cache(), Preferences(), QIcon())
    qtbot.addWidget(preview)
    preview.resize(400, 220)
    preview.show()
    task = Task("https://example.test/video", thumbnail="https://example.test/cover")
    preview.set_task(task)
    image = preview.grab().toImage()
    assert image.pixelColor(10, 100).red() > 80
    assert image.pixelColor(image.width() // 2, image.height() // 2) == QColor("red")
    task.selection = "mp3:320"
    preview.set_task(task)
    assert not preview.current.isNull()


def test_video_details_only_promise_known_container():
    from al_media.ui.task_card import output_details

    task = Task("https://example.test/video", selection="video:1080")
    assert output_details(task, "ru") == ["Видео", "1080p"]
    task.final_path = "D:/video.mkv"
    assert output_details(task, "ru") == ["MKV", "1080p"]
    task.final_path = "D:/video.mp4"
    assert output_details(task, "ru") == ["MP4", "1080p"]


def test_blurred_background_preserves_top_and_bottom_of_portrait(qtbot):
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QPainter

    from al_media.ui.media_preview import blurred_backdrop

    frame = QPixmap(180, 320)
    frame.fill(QColor("green"))
    painter = QPainter(frame)
    painter.fillRect(0, 0, 180, 90, QColor("red"))
    painter.fillRect(0, 230, 180, 90, QColor("blue"))
    painter.end()
    background = blurred_backdrop(frame, QSize(600, 240)).toImage()
    top, bottom = background.pixelColor(100, 30), background.pixelColor(100, 210)
    assert top.red() > top.green() * 2 and bottom.blue() > bottom.green() * 2
