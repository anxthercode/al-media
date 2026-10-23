from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from al_media.models import Task

from .metadata import selection_kind

TIMING = re.compile(r"(\d+):([0-5]\d):([0-5]\d)[,.](\d{3})\s+-->\s+(\d+):([0-5]\d):([0-5]\d)[,.](\d{3})")


def _milliseconds(groups):
    h, m, s, ms = map(int, groups)
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def _timestamp(value):
    value = max(0, value)
    seconds, milliseconds = divmod(value, 1000)
    return f"{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02},{milliseconds:03}"


def clip_srt(text: str, start: float, end: float | None) -> str:
    start_ms, end_ms = round(start * 1000), round(end * 1000) if end is not None else float("inf")
    result = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").lstrip("\ufeff").strip()):
        lines = block.splitlines()
        for index, line in enumerate(lines):
            match = TIMING.search(line)
            if not match:
                continue
            begin, finish = _milliseconds(match.groups()[:4]), _milliseconds(match.groups()[4:])
            if finish <= start_ms or begin >= end_ms:
                break
            begin, finish = max(begin, start_ms) - start_ms, int(min(finish, end_ms)) - start_ms
            result.append(f"{len(result)+1}\n{_timestamp(begin)} --> {_timestamp(finish)}\n" + "\n".join(lines[index+1:]))
            break
    return "\n\n".join(result) + ("\n" if result else "")


@dataclass
class PostprocessPlan:
    destination: Path
    temporary: Path | None
    arguments: list[str]
    stage: str
    program: str = "ffmpeg"


def mp3_encoding_plan(path: Path, rate: int) -> PostprocessPlan:
    temporary = path.with_name(f".{path.stem}.bitrate.mp3")
    arguments = ["-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-map", "0", "-c", "copy",
                 "-c:a", "libmp3lame", "-b:a", f"{rate}k", "-map_metadata", "0", "-progress", "pipe:1", "-nostats", str(temporary)]
    return PostprocessPlan(path, temporary, arguments, "converting")


def postprocess_plans(task: Task, paths: list[str]) -> list[PostprocessPlan]:
    plans = []
    clipping = task.clip_start is not None or task.clip_end is not None
    for filename in paths:
        path = Path(filename)
        if clipping and task.subtitle_language and task.subtitle_mode != "none":
            subtitles = [p for p in path.parent.iterdir() if p.name.startswith(path.stem + ".") and p.name.endswith(f".{task.subtitle_language}.srt")]
            if not subtitles:
                raise ValueError("Requested subtitle file is missing")
            for subtitle in subtitles:
                backup = subtitle.with_name(f".{subtitle.name}.{task.id[:8]}.source")
                if not backup.exists():
                    backup.write_bytes(subtitle.read_bytes())
                clipped = clip_srt(backup.read_text(encoding="utf-8-sig"), task.clip_start or 0, task.clip_end)
                subtitle.write_text(clipped, encoding="utf-8")
                if clipped and task.subtitle_mode == "embedded" and path.suffix == ".mkv":
                    temporary = path.with_name(f".{path.stem}.subtitles{path.suffix}")
                    arguments = ["-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-i", str(subtitle),
                                 "-map", "0", "-map", "1:0", "-c", "copy", "-c:s", "srt", "-metadata:s:s:0",
                                 f"language={task.subtitle_language}", "-progress", "pipe:1", "-nostats", str(temporary)]
                    plans.append(PostprocessPlan(path, temporary, arguments, "embedding_subtitles"))
        if task.selection.startswith("mp3:") and path.suffix.lower() == ".mp3":
            # Generic extractors often omit abr. Inspect the actual MP3 rather
            # than trusting an estimate or re-encoding already suitable audio.
            plans.append(PostprocessPlan(path, None, ["-v", "error", "-select_streams", "a:0", "-show_entries",
                                                      "stream=codec_name,bit_rate", "-of", "json", str(path)], "converting", "ffprobe"))
        if clipping and selection_kind(task.selection) == "video":
            # Some non-seekable HTTP sources return a successful FFmpeg exit
            # with only a container header. Do not report that as a video.
            plans.append(PostprocessPlan(path, None, ["-v", "error", "-select_streams", "v:0", "-show_entries",
                                                      "stream=codec_type,width,height", "-of", "json", str(path)], "postprocessing", "ffprobe"))
    return plans


def cleanup_subtitle_backups(task: Task, paths: list[str]):
    for filename in paths:
        path = Path(filename)
        try:
            for candidate in path.parent.iterdir():
                if candidate.name.startswith("." + path.stem + ".") and candidate.name.endswith(f".{task.id[:8]}.source"):
                    candidate.unlink(missing_ok=True)
        except OSError:
            pass
