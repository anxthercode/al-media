from __future__ import annotations

import math
from urllib.parse import urlsplit

from al_media.models import Task


def parse_urls(text: str) -> tuple[list[str], list[str]]:
    valid, invalid = [], []
    for line in text.splitlines():
        url = line.strip()
        if not url:
            continue
        try:
            parsed = urlsplit(url)
            valid_host = bool(parsed.hostname)
            _ = parsed.port  # Validate malformed/out-of-range ports before queueing.
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


def populate_task(task: Task, info: dict) -> None:
    task.title = str(info.get("title") or info.get("id") or "")
    task.media_id = str(info.get("id") or "")
    task.source = str(info.get("extractor_key") or info.get("extractor") or urlsplit(task.url).hostname or "")
    task.author = str(info.get("artist") or info.get("uploader") or info.get("channel") or "")
    task.thumbnail = str(info.get("thumbnail") or "")
    thumbnails = info.get("thumbnails")
    thumbnails = [item for item in thumbnails if isinstance(item, dict) and str(item.get("url", "")).startswith(("http://", "https://"))] if isinstance(thumbnails, list) else []
    thumbnails.sort(key=lambda item: ((item.get("width") or 0) * (item.get("height") or 0), item.get("preference") or 0), reverse=True)
    ordered = [item["url"] for item in thumbnails]
    task.thumbnail_candidates = list(dict.fromkeys(ordered[:1] + ([task.thumbnail] if task.thumbnail else []) + ordered[1:]))[:4]
    if task.thumbnail_candidates:
        task.thumbnail = task.thumbnail_candidates[0]
    duration = info.get("duration")
    task.duration = float(duration) if isinstance(duration, (int, float)) and math.isfinite(duration) and duration > 0 else None
    supplied = info.get("formats")
    task.formats = [item for item in supplied if isinstance(item, dict)] if isinstance(supplied, list) else []
    if not task.formats and info.get("url") and info.get("_type") != "playlist":
        task.formats = [{key: info.get(key) for key in ("url", "ext", "vcodec", "acodec", "height", "width", "filesize", "filesize_approx", "abr", "tbr", "duration", "http_headers")}]
    if task.duration is None:
        durations = [item["duration"] for item in task.formats if isinstance(item.get("duration"), (int, float))
                     and math.isfinite(item["duration"]) and item["duration"] > 0]
        task.duration = max(durations, default=None)
    if isinstance(info.get("http_headers"), dict):
        for item in task.formats:
            item.setdefault("http_headers", info["http_headers"])
    task.subtitles = info.get("subtitles") if isinstance(info.get("subtitles"), dict) else {}
    task.automatic_captions = info.get("automatic_captions") if isinstance(info.get("automatic_captions"), dict) else {}
    task.audio_languages = sorted({f["language"] for f in task.formats if isinstance(f.get("language"), str) and f.get("acodec") not in (None, "none")})
    groups = {}
    for item in task.formats:
        ident = item.get("format_id")
        if item.get("acodec") in (None, "none") or not isinstance(ident, str):
            continue
        language = str(item.get("language") or "")
        note = str(item.get("format_note") or "").split(",")[0].strip() if item.get("vcodec") in (None, "none") else ""
        if note.casefold() in {"low", "medium", "high", "tiny", "audio only", "default"}:
            note = ""
        group = groups.setdefault((language, note), {"language": language, "label": " · ".join(filter(None, (language, note))), "ids": []})
        group["ids"].append(ident)
    task.audio_tracks = list(groups.values())
    entries = info.get("entries")
    task.playlist_entries = []
    if isinstance(entries, list):
        for index, entry in enumerate(entries, 1):
            if not isinstance(entry, dict):
                continue
            url = entry.get("webpage_url") or entry.get("url")
            task.playlist_entries.append({"index": index, "title": str(entry.get("title") or entry.get("id") or index),
                                          "url": url if isinstance(url, str) and url.startswith(("http://", "https://")) else ""})
    task.playlist = info.get("_type") in {"playlist", "multi_video"} and bool(task.playlist_entries)
    task.playlist_count = len(task.playlist_entries) or None
    task.playlist_first_url = task.playlist_entries[0]["url"] if task.playlist_entries else ""
    task.estimated_size = estimate_size(task)


def video_heights(task: Task) -> list[int]:
    return sorted({int(key.split(":")[1]) for key, _ in available_selections({"formats": task.formats}) if key.startswith("video:")}, reverse=True)


def task_selections(task: Task) -> list[tuple[str, str]]:
    if not task.audio_track_ids and not task.audio_language:
        return available_selections({"formats": task.formats})
    formats = []
    for item in task.formats:
        matches = item.get("format_id") in task.audio_track_ids if task.audio_track_ids else item.get("language") == task.audio_language
        if matches:
            formats.append(item)
        elif item.get("vcodec") not in (None, "none"):
            formats.append({**item, "acodec": "none"})
    return available_selections({"formats": formats})


def source_choices(task: Task, mode: str, audio_format: str = "mp3") -> list[str]:
    choices = [key for key, _ in available_selections({"formats": task.formats})]
    if mode == "video":
        return [key for key in choices if selection_kind(key) == "video" and key != "mp4"
                and key != f"video:{max(video_heights(task), default=0)}"]
    if audio_format == "mp3":
        return [key for key in ("mp3:320", "mp3:192", "mp3:128") if key in choices]
    return [key for key in ("audio", "m4a") if key in choices]


def preferred_selection(task: Task, preferences, wanted: str | None = None) -> str:
    keys = [key for key, _ in available_selections({"formats": task.formats})]
    audio_wanted = f"mp3:{preferences.mp3_bitrate}" if preferences.audio_format == "mp3" else preferences.audio_format
    wanted = wanted or (preferences.video_quality if preferences.media_mode == "video" else audio_wanted)
    if wanted in keys:
        return wanted
    if wanted.startswith("video:"):
        limit = int(wanted.split(":")[1])
        lower = [key for key in keys if key.startswith("video:") and int(key.split(":")[1]) <= limit]
        if lower:
            return lower[0]
    audio_keys = [key for key in keys if selection_kind(key) != "video"]
    if audio_keys and (selection_kind(wanted) != "video" or not any(selection_kind(key) == "video" for key in keys)):
        return audio_wanted if audio_wanted in audio_keys else "audio" if "audio" in audio_keys else audio_keys[0]
    return keys[0] if keys else wanted


def estimate_size(task: Task) -> int | None:
    def size(item):
        value = item.get("filesize") or item.get("filesize_approx")
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
            return int(value)
        bitrate = item.get("tbr") or (item.get("abr") if item.get("vcodec") == "none" else None)
        if task.duration and isinstance(bitrate, (int, float)) and math.isfinite(bitrate) and bitrate > 0:
            return round(task.duration * bitrate * 1000 / 8)
        return None
    formats = task.formats
    if task.selection.startswith("mp3:") and task.duration:
        length = (task.clip_end or task.duration) - (task.clip_start or 0)
        return round(length * int(task.selection.split(":")[1]) * 1000 / 8)
    audio = [f for f in formats if f.get("acodec") not in (None, "none") and f.get("vcodec") == "none"]
    if task.selection == "m4a":
        audio = [f for f in audio if f.get("ext") == "m4a"]
    if task.audio_language:
        audio = [f for f in audio if f.get("language") == task.audio_language]
    if task.audio_track_ids:
        audio = [f for f in audio if f.get("format_id") in task.audio_track_ids]
    audio_size = size(max(audio, key=lambda f: f.get("abr") or f.get("tbr") or 0)) if audio else None
    if selection_kind(task.selection) != "video":
        return audio_size
    videos = [f for f in formats if f.get("vcodec") not in (None, "none")]
    if task.selection.startswith("video:"):
        limit = int(task.selection.split(":")[1])
        videos = [f for f in videos if isinstance(f.get("height"), (int, float)) and f["height"] <= limit]
    if not videos:
        return None
    video = max(videos, key=lambda f: (f.get("height") or 0, f.get("fps") or 0, f.get("tbr") or 0))
    video_size = size(video)
    if video.get("acodec") not in (None, "none"):
        return video_size
    return video_size + audio_size if video_size and audio_size else None
