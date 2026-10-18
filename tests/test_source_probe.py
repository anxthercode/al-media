import sys
from pathlib import Path

from al_media.core.metadata import estimate_size, populate_task
from al_media.core.source_probe import SourceProbe, apply_probe, probe_arguments, probe_candidates
from al_media.models import Task


def reel(url="https://example.test/reel"):
    return Task(url, selection="best", formats=[
        {"url": url + "/audio.m4a", "format_id": "audio", "vcodec": "none", "acodec": "aac", "abr": 64, "tbr": 64},
        {"url": url + "/video.mp4", "format_id": "video", "vcodec": "h264", "acodec": "none", "height": 1920, "tbr": 1400}])


def test_reel_duration_probe_enables_video_and_mp3_size_estimates():
    task = reel()
    apply_probe(task, task.formats[0], {"format": {"duration": "31.09", "size": "244552", "bit_rate": "62927"}})
    assert task.duration == 31.09
    assert estimate_size(task) == round(31.09 * 1400 * 1000 / 8) + 244552
    task.selection = "mp3:320"
    assert estimate_size(task) == 1243600
    task.clip_start, task.clip_end = 10, 20
    assert estimate_size(task) == 400000


def test_metadata_duration_fallback_and_unknown_values():
    task = Task("https://example.test/video")
    populate_task(task, {"duration": float("nan"), "formats": [{"duration": 12.5, "vcodec": "h264", "acodec": "aac", "tbr": 1000}]})
    assert task.duration == 12.5 and estimate_size(task) == 1562500
    apply_probe(task, task.formats[0], {"format": {"duration": "inf", "size": "N/A"}})
    assert task.duration == 12.5
    assert estimate_size(Task(task.url, formats=task.formats)) is None


def test_probe_only_direct_streams_and_filters_headers():
    task = reel()
    task.formats += [{"url": "https://example.test/live.m3u8", "protocol": "m3u8_native", "vcodec": "h264"},
                     {"url": "https://example.test/drm.mp4", "has_drm": True, "vcodec": "h264"}]
    assert [item["format_id"] for item in probe_candidates(task)] == ["audio", "video"]
    stream = {**task.formats[0], "http_headers": {"Referer": "https://example.test/", "Host": "bad", "X-Unsafe": "a\r\nb", "Range": "bytes=0-"}}
    args = probe_arguments(stream)
    assert args[args.index("-headers") + 1] == "Referer: https://example.test/\r\n"
    assert args[-2:] == ["-i", stream["url"]]
    assert "1000000" in args and "5000000" in args


def test_async_probe_cancels_stale_task_and_preserves_current_selection(qtbot, tmp_path, monkeypatch):
    from al_media.core import source_probe

    fixture = tmp_path / "probe.py"
    fixture.write_text('import time; time.sleep(.15); print(\'{"format":{"duration":"31.09","size":"244552"}}\')', encoding="utf-8")
    monkeypatch.setattr(source_probe, "probe_arguments", lambda stream: [str(fixture), stream["url"]])
    probe = SourceProbe(Path(sys.executable))
    received = []
    probe.updated.connect(received.append)
    first, second = reel("https://example.test/old"), reel("https://example.test/new")
    probe.start(first)
    probe.start(second)
    second.selection = "mp3:320"
    qtbot.waitUntil(lambda: bool(received), timeout=3000)
    assert received == [second] and first.duration is None
    assert second.duration == 31.09 and second.selection == "mp3:320"
    probe.shutdown()
