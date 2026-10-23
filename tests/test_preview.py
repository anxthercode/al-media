from al_media.application.images import storyboard_frames
from al_media.core.preview_frames import preview_source
from al_media.models import Task


def test_quick_preview_ignores_stale_poster_and_pauses_frames(qapp, monkeypatch):
    from PySide6.QtGui import QColor, QPixmap

    from al_media.quick.media import MediaViewModel, PreviewProvider

    provider = PreviewProvider()
    preview = MediaViewModel({}, provider)
    callbacks = []
    monkeypatch.setattr(preview.cache, "fetch", lambda url, callback, **kwargs: callbacks.append(callback))
    monkeypatch.setattr(preview.extractor, "set_task", lambda task: None)
    monkeypatch.setattr(preview.extractor, "set_enabled", lambda active: None)
    try:
        preview.set_task(Task("https://example.test/first", thumbnail="https://example.test/old.jpg"))
        preview.set_task(Task("https://example.test/second", thumbnail="https://example.test/new.jpg"))
        old, current = QPixmap(160, 90), QPixmap(160, 90)
        old.fill(QColor("red"))
        current.fill(QColor("blue"))
        callbacks[0](old)
        assert not preview.source
        callbacks[1](current)
        assert provider.images[preview.source.rsplit("/", 1)[1]].pixelColor(0, 0) == QColor("blue")
        preview._frame(0, old)
        preview._frame(1, current)
        assert preview.timer.isActive()
        preview._advance()
        assert provider.images[preview.source.rsplit("/", 1)[1]].pixelColor(0, 0) == QColor("blue")
        preview.setActive(False)
        assert not preview.timer.isActive()
        frozen = preview.source
        preview._advance()
        assert preview.source == frozen
        preview.setActive(True)
        assert preview.timer.isActive()
    finally:
        preview.shutdown()


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
