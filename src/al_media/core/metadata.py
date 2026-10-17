from __future__ import annotations

from urllib.parse import urlsplit


def parse_urls(text: str) -> tuple[list[str], list[str]]:
    valid, invalid = [], []
    for line in text.splitlines():
        url = line.strip()
        if not url:
            continue
        try:
            parsed = urlsplit(url)
            valid_host = bool(parsed.hostname)
        except ValueError:
            invalid.append(url)
            continue
        if parsed.scheme.lower() not in {"http", "https"} or not valid_host or " " in url:
            invalid.append(url)
        elif url not in valid:
            valid.append(url)
    return valid, invalid


def available_selections(info: dict) -> list[tuple[str, str]]:
    supplied = info.get("formats")
    formats = [item for item in supplied if isinstance(item, dict)] if isinstance(supplied, list) else []
    # Generic HTTP media may have no codec metadata until downloaded. Unknown
    # is different from the explicit "none" used for audio-only/storyboard data.
    direct = [f for f in formats if f.get("url", "").startswith(("http://", "https://"))
              and f.get("vcodec") in (None, "none") and f.get("acodec") is None]
    direct_video = [f for f in direct if f.get("vcodec") is None and f.get("ext") in {"mp4", "webm", "mkv", "mov", "avi", "ogv", "flv", "ts"}]
    direct_audio = [f for f in direct if f.get("ext") in {"mp3", "m4a", "aac", "ogg", "opus", "wav", "flac"}]
    video = [f for f in formats if f.get("vcodec") not in (None, "none")] + direct_video
    audio = [f for f in formats if f.get("acodec") not in (None, "none")] + direct_audio
    choices = []
    if video:
        choices.append(("best", "Best available video"))
        heights = sorted({int(f["height"]) for f in video if isinstance(f.get("height"), (int, float)) and f["height"] > 0}, reverse=True)
        for height in heights:
            choices.append((f"video:{height}", f"{height}p"))
        if any(f.get("ext") == "mp4" for f in video):
            choices.append(("mp4", "MP4 if available"))
    if audio:
        choices.append(("audio", "Best source audio"))
        if any(f.get("ext") == "m4a" for f in audio):
            choices.append(("m4a", "M4A source"))
    if audio or direct_video:
        choices.extend((f"mp3:{rate}", f"MP3 encode {rate} kbps") for rate in (128, 192, 320))
    return choices


def selection_kind(selection: str) -> str:
    if selection.startswith("mp3:"):
        return "mp3"
    return "audio" if selection in {"audio", "m4a"} else "video"
