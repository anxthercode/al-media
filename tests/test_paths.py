from al_media.config import validate_folder
from al_media.core.metadata import available_selections, parse_urls


def test_unicode_folder_and_urls(tmp_path):
    assert validate_folder(str(tmp_path / "Мои видео")).is_dir()
    good, bad = parse_urls(" https://example.test/a \nhttps://example.test/a\nnot a URL")
    assert good == ["https://example.test/a"]
    assert bad == ["not a URL"]


def test_format_availability():
    assert available_selections({}) == []
    choices = available_selections({"formats": [{"vcodec": "h264", "acodec": "none", "height": 720}]})
    assert ("video:720", "720p") in choices
    assert not any(key.startswith("mp3") for key, _ in choices)


def test_bad_ipv6_url_does_not_raise():
    good, bad = parse_urls("https://[broken/path")
    assert not good and bad


def test_direct_mp4_with_unknown_codecs_can_be_downloaded():
    choices = dict(available_selections({"formats": [{"url": "https://example.test/video.mp4", "ext": "mp4", "vcodec": None}]}))
    assert "best" in choices
    assert "mp3:192" in choices


def test_quality_does_not_offer_upscaling_for_720p_source():
    choices = dict(available_selections({"formats": [{"vcodec": "h264", "height": 720}]}))
    assert "video:720" in choices
    assert "video:2160" not in choices


def test_direct_audio_with_unknown_audio_codec_is_downloadable():
    choices = dict(available_selections({"formats": [{"url": "https://example.test/audio.ogg", "ext": "ogg", "vcodec": "none"}]}))
    assert "audio" in choices
    assert "mp3:192" in choices
    assert "best" not in choices
