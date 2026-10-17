from pathlib import Path

from al_media.config import app_root


def bundled_tools() -> dict[str, Path]:
    """Use the packaged, pinned executables; never check or install updates at runtime."""
    root = app_root() / "tools"
    return {name: root / (name + ".exe") for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno")}
