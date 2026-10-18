from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from al_media.models import Task


def safe_component(value: str, fallback="Media") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:140].rstrip(" .")
    if not value:
        return fallback
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value = "_" + value
    return value


def configure_destination(task: Task, preferences) -> None:
    if not task.folder_configured:
        folder = Path(task.folder or preferences.folder)
        value = {"source": task.source, "author": task.author, "playlist": task.playlist_title}.get(preferences.subfolders, "")
        if value:
            folder /= safe_component(value)
        task.folder = str(folder)
        task.folder_configured = True
    if task.output_stem or task.naming_version == 1:
        return
    title = task.title or task.media_id or "Media"
    if preferences.name_style == "artist_title" and task.author:
        title = f"{task.author} — {title}"
    if task.playlist_index is not None:
        title = f"{task.playlist_index:02} — {title}"
    stem = safe_component(title)
    # A task-specific suffix keeps parts resumable and different formats distinct.
    # It also avoids overwriting an unrelated file with the same title.
    choices = (task.selection, task.clip_start, task.clip_end, task.audio_language, task.audio_track_ids, task.subtitle_language, task.subtitle_auto, task.subtitle_mode)
    fingerprint = hashlib.blake2s(repr(choices).encode(), digest_size=2).hexdigest()
    task.output_stem = f"{stem} [{task.id[:8]}-{fingerprint}]"


def publish_files(task: Task, filenames: list[str]) -> list[str]:
    """Publish complete files under readable names, preserving resume templates.

    On Windows rename refuses to replace an existing destination. Numbering is
    checked for the whole family (media and sidecars), and races retry safely.
    """
    published = []
    for filename in filenames:
        source = Path(filename)
        title = task.title or task.media_id or "Media"
        if task.output_stem:
            # Keep the remembered naming choice and playlist prefix; remove only
            # our exact suffix, never text or an extension supplied by the author.
            marker = f" [{task.id[:8]}-"
            title = task.output_stem.rsplit(marker, 1)[0]
        stem = safe_component(title)
        companions = [path for path in source.parent.iterdir()
                      if path.is_file() and path.name.startswith(source.stem + ".") and path != source
                      and path.suffix.lower() in {".srt", ".vtt", ".ass", ".lrc", ".jpg", ".png", ".webp"}]
        number = 1
        while True:
            name = stem + (f" ({number})" if number > 1 else "")
            destination = source.with_name(name + source.suffix)
            pairs = [(path, path.with_name(name + path.name[len(source.stem):])) for path in companions]
            if destination == source:
                published.append(str(source))
                break
            if any(target.exists() for target in [destination, *(target for _, target in pairs)]):
                number += 1
                continue
            try:
                if os.name == "nt":
                    source.rename(destination)
                else:
                    os.link(source, destination)
                    source.unlink()
            except FileExistsError:
                number += 1
                continue
            for path, target in pairs:
                if os.name == "nt":
                    path.rename(target)
                else:
                    os.link(path, target)
                    path.unlink()
            published.append(str(destination))
            break
    return published


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        return "youtube:" + parsed.path.strip("/").split("/")[0]
    query = dict(parse_qsl(parsed.query))
    if host in {"youtube.com", "music.youtube.com"}:
        ident = query.get("v")
        if not ident and parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
            ident = parsed.path.split("/")[2]
        if ident:
            return "youtube:" + ident
    ignored = {"fbclid", "gclid", "igsh", "igshid", "si", "feature"}
    clean = sorted((key, value) for key, value in parse_qsl(parsed.query) if key not in ignored and not key.startswith("utm_"))
    return urlunsplit(("https", host + (f":{parsed.port}" if parsed.port else ""), parsed.path.rstrip("/"), urlencode(clean), ""))


def same_result(left: Task, right: Task) -> bool:
    from .metadata import video_heights

    source = left.media_id and right.media_id and left.media_id == right.media_id and left.source.casefold() == right.source.casefold()
    if left.source.casefold() == "generic" and urlsplit(left.url).hostname != urlsplit(right.url).hostname:
        source = False
    if not source and canonical_url(left.url) != canonical_url(right.url):
        return False
    def selection(task):
        return f"video:{max(video_heights(task), default=0)}" if task.selection == "best" else task.selection
    return (selection(left), left.clip_start, left.clip_end, left.audio_language, left.audio_track_ids, left.subtitle_language, left.subtitle_auto, left.subtitle_mode) == (
        selection(right), right.clip_start, right.clip_end, right.audio_language, right.audio_track_ids, right.subtitle_language, right.subtitle_auto, right.subtitle_mode)
