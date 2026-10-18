from pathlib import Path

import pytest

from al_media.config import Preferences
from al_media.core.commands import download_args
from al_media.core.metadata import parse_urls, populate_task, preferred_selection, task_selections, video_heights
from al_media.core.naming import canonical_url, configure_destination, publish_files, same_result
from al_media.core.postprocess import clip_srt, mp3_encoding_plan, postprocess_plans
from al_media.models import State, Task

TOOLS = {name: Path("C:/Tools") / (name + ".exe") for name in ("yt-dlp", "ffmpeg", "deno")}


def test_invalid_port_is_rejected_before_queueing():
    urls = ["https://example.test:invalid/video", "https://example.test:99999/video"]
    assert parse_urls("\n".join(urls)) == ([], urls)


def test_source_resolution_is_never_limited_to_presets():
    for maximum in (480, 2160, 4320, 6144):
        task = Task("https://example.test/video")
        populate_task(task, {"id": "abc", "formats": [{"height": maximum, "vcodec": "av1", "acodec": "none"},
                                                           {"height": 360, "vcodec": "h264", "acodec": "none"}]})
        assert video_heights(task) == [maximum, 360]


def test_mp3_default_for_audio_only_source():
    task = Task("https://example.test/audio", formats=[{"vcodec": "none", "acodec": "mp3", "ext": "mp3", "abr": 128}])
    assert preferred_selection(task, Preferences()) == "mp3:320"
    args = download_args(task, TOOLS, Preferences())
    assert "--no-update" in args


def test_distinct_voice_tracks_filter_audio_formats_and_commands():
    task = Task("https://example.test/video", selection="m4a")
    populate_task(task, {"formats": [
        {"format_id": "v2160", "vcodec": "av1", "acodec": "none", "height": 2160},
        {"format_id": "a-original", "vcodec": "none", "acodec": "aac", "ext": "m4a", "language": "en", "format_note": "Original, medium"},
        {"format_id": "a-dub-1", "vcodec": "none", "acodec": "opus", "ext": "webm", "language": "en", "format_note": "Voice over, low"},
        {"format_id": "a-dub-2", "vcodec": "none", "acodec": "opus", "ext": "webm", "language": "en", "format_note": "Voice over, medium"},
    ]})
    assert len(task.audio_tracks) == 2
    task.audio_track_ids = task.audio_tracks[1]["ids"]
    assert task.audio_track_ids == ["a-dub-1", "a-dub-2"]
    keys = {key for key, _ in task_selections(task)}
    assert "m4a" not in keys and {"audio", "video:2160"} <= keys
    task.selection = "best"
    selector = download_args(task, TOOLS, Preferences())
    selector = selector[selector.index("-f") + 1]
    assert r"a\-dub\-1|a\-dub\-2" in selector and "a-original" not in selector


def test_voice_change_has_distinct_duplicate_identity():
    left = Task("https://example.test/video", audio_track_ids=["one"])
    right = Task("https://example.test/video", audio_track_ids=["two"])
    assert not same_result(left, right)


def test_clip_track_subtitles_and_music_args():
    task = Task("https://example.test/video", clip_start=80, clip_end=225, audio_language="en", subtitle_language="be",
                subtitle_mode="embedded", selection="video:2160")
    args = download_args(task, TOOLS, Preferences())
    assert args[args.index("--download-sections") + 1] == "*80-225"
    assert "--force-keyframes-at-cuts" in args
    assert "ba[language=en]" in args[args.index("-f") + 1]
    assert "--write-subs" in args and "--convert-subs" in args
    assert "--embed-subs" not in args  # clipped captions are shifted before embedding
    assert args[args.index("--remux-video") + 1] == "mkv"
    task.selection, task.thumbnail = "mp3:320", "https://example.test/cover.jpg"
    args = download_args(task, TOOLS, Preferences())
    assert "320K" in args and "--embed-metadata" in args and "--embed-thumbnail" in args
    assert "--force-keyframes-at-cuts" not in args
    assert args[-2:] == ["--", task.url]


@pytest.mark.parametrize("start,end", [(float("nan"), 10), (-1, 10), (20, 10), (0, float("inf"))])
def test_invalid_clip_never_reaches_engine(start, end):
    with pytest.raises(ValueError):
        download_args(Task("https://example.test/video", clip_start=start, clip_end=end), TOOLS, Preferences())


def test_clipped_subtitles_are_shifted_and_trimmed():
    text = "1\n00:00:01,000 --> 00:00:05,000\nBefore\n\n2\n00:00:08,000 --> 00:00:14,000\nOverlap start\n\n3\n00:00:18,000 --> 00:00:25,000\nOverlap end\n"
    assert clip_srt(text, 10, 20) == "1\n00:00:00,000 --> 00:00:04,000\nOverlap start\n\n2\n00:00:08,000 --> 00:00:10,000\nOverlap end\n"


def test_mp3_source_not_inflated_but_lower_target_reencoded(tmp_path):
    path = tmp_path / "music.mp3"
    task = Task("https://example.test/audio", selection="mp3:320", formats=[{"ext": "mp3", "abr": 128}])
    assert postprocess_plans(task, [str(path)])[0].program == "ffprobe"
    task.formats = [{"ext": "mp3", "abr": 320}]
    task.selection = "mp3:128"
    plans = postprocess_plans(task, [str(path)])
    assert len(plans) == 1 and plans[0].program == "ffprobe"
    assert "128k" in mp3_encoding_plan(path, 128).arguments


def test_duplicate_recognition_ignores_tracking_and_distinguishes_results():
    assert canonical_url("https://youtu.be/abc?si=123") == canonical_url("https://www.youtube.com/watch?v=abc&utm_source=test")
    left = Task("https://youtu.be/abc", selection="mp3:320")
    right = Task("https://youtube.com/watch?v=abc", selection="mp3:320")
    assert same_result(left, right)
    right.clip_start, right.clip_end = 10, 20
    assert not same_result(left, right)
    right.clip_start = right.clip_end = None
    right.selection = "best"
    assert not same_result(left, right)


def test_manual_and_automatic_captions_produce_distinct_results(tmp_path):
    from dataclasses import replace

    left = Task("https://example.test/video", title="Video", subtitle_language="en", subtitle_mode="sidecar")
    right = replace(left, subtitle_auto=True)
    assert not same_result(left, right)
    for task in (left, right):
        configure_destination(task, Preferences(folder=str(tmp_path)))
    assert left.output_stem != right.output_stem


def test_naming_is_stable_for_resume_and_windows_safe(tmp_path):
    prefs = Preferences(folder=str(tmp_path), name_style="artist_title", subfolders="playlist")
    task = Task("https://example.test/video", title='Track: "Name"?', author="Artist", playlist_title="Album / Mix", playlist_index=2)
    configure_destination(task, prefs)
    first = (task.folder, task.output_stem)
    assert Path(task.folder).parent == tmp_path
    assert task.output_stem.startswith("02 — Artist — Track_")
    configure_destination(task, prefs)
    assert first == (task.folder, task.output_stem)


def test_old_task_keeps_legacy_output_template_for_resume(tmp_path):
    task = Task.from_dict({"id": "123456789", "url": "https://example.test/video", "state": "interrupted", "folder": str(tmp_path)})
    configure_destination(task, Preferences(folder=str(tmp_path), subfolders="source"))
    assert task.naming_version == 1 and not task.output_stem
    assert "[12345678]" in download_args(task, TOOLS, Preferences())[download_args(task, TOOLS, Preferences()).index("-o") + 1]


def test_readable_name_keeps_author_title_and_never_replaces_files(tmp_path):
    prefs = Preferences(folder=str(tmp_path))
    for index in (1, 2):
        task = Task("https://example.test/song", title="Song.mp3", selection="mp3:320")
        configure_destination(task, prefs)
        working = tmp_path / (task.output_stem + ".mp3")
        working.write_bytes(str(index).encode())
        names = publish_files(task, [str(working)])
        expected = "Song.mp3.mp3" if index == 1 else "Song.mp3 (2).mp3"
        assert Path(names[0]).name == expected
        assert Path(names[0]).read_bytes() == str(index).encode()
        assert not working.exists()
    assert (tmp_path / "Song.mp3.mp3").read_bytes() == b"1"


def test_sidecars_follow_published_media_without_overwrite(tmp_path):
    task = Task("https://example.test/video", title="Video", subtitle_language="en", subtitle_mode="sidecar")
    configure_destination(task, Preferences(folder=str(tmp_path)))
    working = tmp_path / (task.output_stem + ".mkv")
    sidecar = tmp_path / (task.output_stem + ".en.srt")
    working.write_bytes(b"video")
    sidecar.write_text("captions", encoding="utf-8")
    (tmp_path / "Video.en.srt").write_text("existing", encoding="utf-8")
    result = publish_files(task, [str(working)])
    assert Path(result[0]).name == "Video (2).mkv"
    assert (tmp_path / "Video (2).en.srt").read_text(encoding="utf-8") == "captions"
    assert (tmp_path / "Video.en.srt").read_text(encoding="utf-8") == "existing"


def test_duplicate_completed_file_can_be_found_after_clear(qtbot, tmp_path):
    from al_media.core.scheduler import Scheduler
    from al_media.database import Database
    path = tmp_path / "video.mp4"
    path.write_bytes(b"media")
    db = Database(tmp_path / "db.sqlite3")
    previous = Task("https://youtu.be/abc", state=State.COMPLETED, final_path=str(path), hidden=True)
    db.save(previous)
    scheduler = Scheduler(db, TOOLS, Preferences(folder=str(tmp_path)))
    assert scheduler.find_duplicate(Task("https://youtube.com/watch?v=abc")).id == previous.id
    db.close()
