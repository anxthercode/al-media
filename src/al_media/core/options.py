from __future__ import annotations

import math

from al_media.core.metadata import task_selections


def parse_time(value: str) -> float | None:
    if not value.strip():
        return None
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) > 3:
        raise ValueError("time")
    numbers = [float(part) for part in parts]
    if any(not math.isfinite(part) or part < 0 for part in numbers):
        raise ValueError("time")
    if len(numbers) > 1 and any(part >= 60 for part in numbers[1:]):
        raise ValueError("time")
    result = 0.0
    for part in numbers:
        result = result * 60 + part
    return result


def format_time(value):
    if value is None:
        return ""
    seconds = int(value)
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{value % 60:06.3f}".rstrip("0").rstrip(".")


def apply_options(task, clip, start_text, end_text, track, subtitles, subtitle_mode):
    start = end = None
    if clip:
        start = parse_time(start_text) or 0.0
        end = parse_time(end_text)
        if end is not None and end <= start or task.duration is not None and (start >= task.duration or end is not None and end > task.duration):
            raise ValueError("range")
        if end is None:
            end = task.duration
        if start == 0 and end is None:
            raise ValueError("range")
    before = (task.clip_start, task.clip_end, task.audio_language, tuple(task.audio_track_ids), task.subtitle_language, task.subtitle_auto, task.subtitle_mode)
    task.clip_start, task.clip_end = start, end
    task.audio_language = track.get("language", "") if isinstance(track, dict) else track or ""
    task.audio_track_ids = list(track["ids"]) if isinstance(track, dict) else []
    task.subtitle_language = subtitles[0] if subtitles else ""
    task.subtitle_auto = bool(subtitles and subtitles[1])
    task.subtitle_mode = subtitle_mode if subtitles else "none"
    if task.selection == "m4a" and "m4a" not in {key for key, _ in task_selections(task)}:
        task.selection = "audio"
    after = (task.clip_start, task.clip_end, task.audio_language, tuple(task.audio_track_ids), task.subtitle_language, task.subtitle_auto, task.subtitle_mode)
    if before != after:
        task.output_stem = ""
        task.naming_version = 2
