from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from al_media.models import Task

# One choice per language, with human captions preferred over generated ones.
# Include the four interface languages alongside widely used subtitle languages.
SUBTITLE_LANGUAGES = ("ru", "en", "uk", "be", "de", "fr", "es", "pt", "zh", "ja")
LANGUAGE_TAGS = dict(zip(SUBTITLE_LANGUAGES, ("rus", "eng", "ukr", "bel", "deu", "fra", "spa", "por", "zho", "jpn"), strict=True))


def subtitle_tag(code: str) -> str:
    language = code.replace("_", "-").split("-")[0].lower()
    return LANGUAGE_TAGS.get(language, language)


def subtitle_choices(task: Task) -> list[tuple[str, bool, str]]:
    choices = []
    for language in SUBTITLE_LANGUAGES:
        for automatic, supplied in ((False, task.subtitles), (True, task.automatic_captions)):
            candidates = [code for code, formats in supplied.items()
                          if formats and code.replace("_", "-").split("-")[0].lower() == language]
            if candidates:
                # YouTube's -orig track avoids an unnecessary translated request.
                code = min(candidates, key=lambda code: (not (automatic and code.endswith("-orig")), code != language, code))
                choices.append((code, automatic, language))
                break
    return choices


def subtitle_delay(task: Task) -> int:
    """YouTube translated caption URLs need time after extraction (yt-dlp #13831)."""
    host = (urlsplit(task.url).hostname or "").lower()
    if task.subtitle_auto and host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}:
        formats = task.automatic_captions.get(task.subtitle_language, [])
        if any(parse_qs(urlsplit(item.get("url", "")).query).get("tlang") for item in formats):
            return 60
    return 2
