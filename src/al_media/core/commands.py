from __future__ import annotations

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
    args = [*common_args(tools, preferences), "--yes-playlist" if task.playlist else "--no-playlist",
            "--newline", "--progress", "--no-simulate", "--no-overwrites", "--continue", "--part", "--paths", task.folder,
            "-o", f"%(title).180B [%(id)s] [{task.id[:8]}].%(ext)s",
            "--progress-template", "download:ALM_PROGRESS:download|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s|%(progress._percent_str)s",
            "--progress-template", "postprocess:ALM_PROGRESS:postprocess|NA|NA|NA|NA|NA|NA",
            "--print", "before_dl:ALM_INFO:%(.{id,title,extractor_key,uploader,duration})j",
            "--print", "after_move:ALM_FILE:%(filepath)j"]
    if task.selection.startswith("mp3:"):
        args += ["-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--audio-quality", task.selection.split(":")[1] + "K"]
    elif task.selection == "audio":
        args += ["-f", "bestaudio/best", "-x"]
    elif task.selection == "m4a":
        args += ["-f", "bestaudio[ext=m4a]"]
    elif task.selection == "mp4":
        args += ["-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best", "--merge-output-format", "mp4"]
    elif task.selection.startswith("video:"):
        limit = int(task.selection.split(":")[1])
        args += ["-f", f"bv*[height<={limit}]+ba/b[height<={limit}]", "--merge-output-format", "mkv/mp4"]
    else:
        args += ["-f", "bv*+ba/b", "--merge-output-format", "mkv/mp4"]
    return [*args, "--", task.url]
