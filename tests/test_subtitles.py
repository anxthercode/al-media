from pathlib import Path

import pytest

from al_media.config import Preferences
from al_media.core.commands import download_args
from al_media.core.errors import classify_engine_error
from al_media.core.postprocess import SubtitlesUnavailable, cleanup_subtitle_backups, postprocess_plans
from al_media.core.subtitles import SUBTITLE_LANGUAGES, subtitle_choices, subtitle_delay
from al_media.models import Task

TOOLS = {name: Path("C:/Tools") / (name + ".exe") for name in ("yt-dlp", "ffmpeg", "deno")}


def test_language_choices_are_bounded_and_prefer_manual_then_original_captions():
    task = Task("https://youtube.com/watch?v=abc")
    task.subtitles = {"en-US": [{"ext": "vtt"}], "live_chat": [{"ext": "json"}], "xx": [{"ext": "vtt"}]}
    task.automatic_captions = {code: [{"ext": "vtt"}] for code in (*SUBTITLE_LANGUAGES, "xx", "en-orig", "ru-orig", "zh-Hant")}
    choices = subtitle_choices(task)
    assert len(choices) == 10 and len({language for _, _, language in choices}) == 10
    assert ("en-US", False, "en") in choices
    assert ("ru-orig", True, "ru") in choices
    assert all(code not in {"xx", "live_chat"} for code, _, _ in choices)


def test_only_translated_youtube_captions_get_the_required_wait():
    task = Task("https://youtube.com/watch?v=abc", subtitle_auto=True, subtitle_language="ru", subtitle_mode="embedded")
    task.automatic_captions = {"ru": [{"url": "https://www.youtube.com/api/timedtext?lang=en&tlang=ru"}]}
    assert subtitle_delay(task) == 60
    args = download_args(task, TOOLS, Preferences())
    assert args[args.index("--sleep-subtitles") + 1] == "60"
    task.automatic_captions["ru"][0]["url"] = "https://www.youtube.com/api/timedtext?lang=ru"
    assert subtitle_delay(task) == 2
    task.automatic_captions["ru"][0]["url"] += "&tlang=en"
    task.url = "https://youtube.com.evil.test/watch?v=abc"
    assert subtitle_delay(task) == 2


@pytest.mark.parametrize("clipping", [False, True])
def test_embedding_uses_one_verified_mux_and_cleans_only_task_subtitles(tmp_path, clipping):
    task = Task("https://example.test/video", subtitle_language="ru", subtitle_mode="embedded")
    if clipping:
        task.clip_start, task.clip_end = 2, 4
    media = tmp_path / "video [task].mkv"
    media.write_bytes(b"fixture")
    subtitle = tmp_path / "video [task].ru.srt"
    subtitle.write_text("1\n00:00:01,000 --> 00:00:05,000\nHello\n", encoding="utf-8")
    unrelated = tmp_path / "video.ru.srt"
    unrelated.write_text("keep", encoding="utf-8")
    plans = postprocess_plans(task, [str(media)])
    assert plans[0].stage == plans[1].stage == "embedding_subtitles"
    assert plans[0].program == "ffmpeg" and plans[1].program == "ffprobe"
    assert "language=rus" in plans[0].arguments
    assert "--embed-subs" not in download_args(task, TOOLS, Preferences())
    assert subtitle.is_file()  # Retained until successful mux and verification.
    if clipping:
        assert "00:00:00,000 --> 00:00:02,000" in subtitle.read_text(encoding="utf-8")
        assert postprocess_plans(task, [str(media)])  # Retrying must not shift twice.
        assert "00:00:00,000 --> 00:00:02,000" in subtitle.read_text(encoding="utf-8")
    cleanup_subtitle_backups(task, [str(media)])
    assert not subtitle.exists() and unrelated.read_text(encoding="utf-8") == "keep"


def test_missing_selected_subtitles_are_not_reported_as_success(tmp_path):
    task = Task("https://example.test/video", subtitle_language="en", subtitle_mode="embedded")
    with pytest.raises(SubtitlesUnavailable):
        postprocess_plans(task, [str(tmp_path / "video.mkv")])
    assert classify_engine_error(["ERROR: Unable to download video subtitles for 'ru': HTTP Error 429: Too Many Requests"]) == "error_subtitles_rate_limit"
    assert classify_engine_error(["ERROR: HTTP Error 429: Too Many Requests"]) == "error_rate_limit"
