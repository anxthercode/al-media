from __future__ import annotations

import math
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from al_media.config import Preferences
from al_media.models import Task


def common_args(tools: dict[str, Path], preferences: Preferences) -> list[str]:
    args = ["--ignore-config", "--no-update", "--no-color", "--encoding", "utf-8", "--js-runtimes", f"deno:{tools['deno']}", "--ffmpeg-location", str(tools["ffmpeg"].parent),
            "--socket-timeout", "20", "--retries", "2", "--extractor-retries", "2"]
    # Public-media mode. Never import a browser session or a stale cookie setting.
    return args


def metadata_args(url: str, tools: dict[str, Path], preferences: Preferences, playlist: bool = False) -> list[str]:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    playlist = playlist or (parsed.path.rstrip("/") == "/playlist" and bool(query.get("list")))
    return [*common_args(tools, preferences), "-J", "--flat-playlist" if playlist else "--no-playlist", "--", url]


def download_args(task: Task, tools: dict[str, Path], preferences: Preferences) -> list[str]:
    output = task.output_stem.replace("%", "%%") + ".%(ext)s" if task.output_stem else f"%(title).180B [%(id)s] [{task.id[:8]}].%(ext)s"
    args = [*common_args(tools, preferences), "--yes-playlist" if task.playlist else "--no-playlist",
            "--newline", "--progress", "--progress-delta", "0.25", "--no-simulate", "--no-overwrites", "--continue", "--part", "--paths", task.folder,
            "-o", output, "--windows-filenames",
            "--progress-template", "download:ALM_PROGRESS:download|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s|%(progress._percent_str)s",
            "--progress-template", "postprocess:ALM_PROGRESS:postprocess|NA|NA|NA|NA|NA|NA",
            "--print", "before_dl:ALM_INFO:%(.{id,title,extractor_key,uploader,duration})j",
            "--print", "after_move:ALM_FILE:%(filepath)j"]
    language = ""
    if task.audio_language:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", task.audio_language):
            raise ValueError("Invalid audio language")
        language = f"[language={task.audio_language}]"
    if task.audio_track_ids:
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value) for value in task.audio_track_ids):
            raise ValueError("Invalid audio track")
        pattern = "|".join(re.escape(value) for value in task.audio_track_ids)
        language = f"[format_id~='^(?:{pattern})$']"
    audio = f"bestaudio{language}/best{language}"
    if task.selection.startswith("mp3:"):
        rate = int(task.selection.split(":")[1])
        if rate not in {128, 192, 320}:
            raise ValueError("Invalid MP3 bitrate")
        args += ["-f", f"bestaudio[ext=mp3]{language}/{audio}", "-x", "--audio-format", "mp3", "--audio-quality", f"{rate}K"]
    elif task.selection == "audio":
        args += ["-f", audio, "-x"]
    elif task.selection == "m4a":
        args += ["-f", f"bestaudio[ext=m4a]{language}"]
    elif task.selection == "mp4":
        args += ["-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best", "--merge-output-format", "mp4"]
    elif task.selection.startswith("video:"):
        limit = int(task.selection.split(":")[1])
        video = "bv" if language else "bv*"
        args += ["-f", f"{video}[height<={limit}]+ba{language}/b[height<={limit}]{language}", "--merge-output-format", "mkv/mp4"]
    else:
        args += ["-f", f"bv+ba{language}/b{language}" if language else "bv*+ba/b", "--merge-output-format", "mkv/mp4"]
    is_audio = task.selection in {"audio", "m4a"} or task.selection.startswith("mp3:")
    if is_audio and preferences.music_tags:
        args += ["--embed-metadata", "--no-embed-info-json"]
    if is_audio and preferences.music_cover and task.thumbnail:
        args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
    clipping = task.clip_start is not None or task.clip_end is not None
    if clipping:
        start, end = task.clip_start or 0, task.clip_end
        if not math.isfinite(start) or start < 0 or end is not None and (not math.isfinite(end) or end <= start):
            raise ValueError("Invalid time range")
        args += ["--download-sections", f"*{start:g}-" + (f"{end:g}" if end is not None else "inf")]
        if not is_audio:
            # Exact cuts re-encode. FFmpeg's container defaults can otherwise
            # choose MPEG-4 at ~200 kbit/s, even for a 4K source. VP9 ships in
            # our LGPL build; explicit constant quality preserves detail and
            # two threads leave the desktop responsive during concurrent jobs.
            args += ["--force-keyframes-at-cuts", "--downloader-args",
                     "ffmpeg_i:-threads 2", "--downloader-args",
                     "ffmpeg_o:-c:v libvpx-vp9 -crf 18 -b:v 0 -deadline good -cpu-used 4 -row-mt 1 -threads 2 -filter_threads 1 -c:a copy"]
    if task.subtitle_language and task.subtitle_mode != "none":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", task.subtitle_language):
            raise ValueError("Invalid subtitle language")
        args += ["--write-auto-subs" if task.subtitle_auto else "--write-subs", "--sub-langs", re.escape(task.subtitle_language),
                 "--sub-format", "srt/vtt/best", "--convert-subs", "srt"]
        if task.subtitle_mode == "embedded" and not is_audio:
            args += ["--remux-video", "mkv"]
            if not clipping:
                args += ["--embed-subs"]
    return [*args, "--", task.url]
