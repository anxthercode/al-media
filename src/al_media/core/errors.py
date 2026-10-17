from __future__ import annotations

from collections.abc import Sequence


def classify_engine_error(lines: Sequence[str]) -> str:
    """Return a safe, stable error code based on the final yt-dlp error.

    Warnings often mention cookies even when the actual failure is unrelated.
    Prefer ERROR lines so the UI does not misdiagnose a later network or format
    failure as an authorization problem. Never persist raw process output.
    """
    errors = [line for line in lines if "ERROR:" in line.upper()]
    text = "\n".join(errors[-3:] if errors else lines[-10:]).lower()
    if "unsupported url" in text or "no suitable extractor" in text:
        return "error_unsupported_url"
    if "sign in to confirm" in text and "not a bot" in text:
        return "error_youtube_verification"
    if "cookie" in text and any(term in text for term in ("could not copy", "failed to decrypt", "dpapi", "database", "netscape", "could not find")):
        return "error_cookies_unreadable"
    if "private video" in text or "private media" in text:
        return "error_private_media"
    if "sign in" in text or "login" in text or "cookies" in text:
        return "error_auth_required"
    if "video is unavailable" in text or "video unavailable" in text:
        return "error_unavailable"
    if "geo" in text or "country" in text:
        return "error_geo"
    if "429" in text or "rate limit" in text:
        return "error_rate_limit"
    if "403" in text or "http error" in text and "forbidden" in text:
        return "error_media_forbidden"
    if "requested format is not available" in text:
        return "error_no_formats"
    if "ffmpeg" in text:
        return "error_ffmpeg"
    if "deno" in text or "javascript runtime" in text:
        return "error_deno"
    if "space left" in text or "disk full" in text:
        return "error_disk_full"
    if "permission" in text or "access is denied" in text:
        return "error_folder_denied"
    if "timed out" in text or "network" in text or "dns" in text or "resolve" in text:
        return "error_network"
    return "error_engine"
