from pathlib import Path

from al_media.config import Preferences
from al_media.core.commands import download_args, metadata_args, youtube_playlist_urls
from al_media.models import Task

TOOLS = {name: Path("C:/Program Files/ALM") / (name + ".exe") for name in
         ("yt-dlp", "ffmpeg", "deno")}


def test_safe_url_and_runtime_args():
    url = "https://example.test/video?a=$(echo bad)&list=x"
    args = metadata_args(url, TOOLS, Preferences())
    assert args[-2:] == ["--", url]
    assert "--no-playlist" in args
    assert f"deno:{TOOLS['deno']}" in args


def test_video_audio_and_final_print():
    task = Task("https://example.test/a", folder="C:/Загрузки")
    task.selection = "mp3:192"
    args = download_args(task, TOOLS, Preferences())
    assert args[args.index("--audio-quality") + 1] == "192K"
    assert "after_move:ALM_FILE:%(filepath)j" in args
    assert args[-2] == "--"
    task.selection = "video:720"
    args = download_args(task, TOOLS, Preferences())
    assert "bv*[height<=720]+ba/b[height<=720]" in args


def test_playlist_metadata_is_flat_but_video_with_list_stays_single():
    assert "--flat-playlist" in metadata_args("https://youtube.com/playlist?list=PL123", TOOLS, Preferences())
    assert "--no-playlist" in metadata_args("https://youtube.com/watch?v=123&list=PL123", TOOLS, Preferences())
    args = metadata_args("https://soundcloud.com/author/sets/album", TOOLS, Preferences())
    assert "--flat-playlist" in args
    assert "--yes-playlist" in metadata_args("https://youtube.com/watch?v=123&list=PL123", TOOLS, Preferences(), True)


def test_youtube_playlist_context_is_host_checked_and_separates_sources():
    expected = ("https://www.youtube.com/watch?v=abc", "https://www.youtube.com/playlist?list=PL123")
    assert youtube_playlist_urls("https://www.youtube.com/watch?v=abc&list=PL123&index=5") == expected
    assert youtube_playlist_urls("https://youtu.be/abc?list=PL123&si=tracking") == expected
    for url in ("https://youtube.com.evil.test/watch?v=abc&list=PL123", "https://example.test/watch?v=abc&list=x", "https://youtube.com/playlist?list=PL123", "https://youtu.be/abc"):
        assert youtube_playlist_urls(url) is None


def test_stale_browser_settings_do_not_affect_public_downloads():
    prefs = Preferences()
    prefs.cookie_mode = "browser"
    prefs.cookie_browser = "chrome"
    args = metadata_args("https://youtube.com/watch?v=123", TOOLS, prefs)
    assert "--cookies-from-browser" not in args
    assert "--cookies" not in args
    assert "--ignore-config" in args
    assert "--no-update" in args
