from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

PROFILE_ID = "ALMedia"
# Keep existing profiles usable after the product rename; fresh installs use ALMedia.
LEGACY_PROFILE_ID = "UniversalMediaStudio"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        return executable_dir if (executable_dir / "tools").is_dir() else Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def data_root() -> Path:
    executable_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else app_root()
    if (executable_dir / "portable.flag").exists():
        root = executable_dir / "data"
    else:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
        root = base / PROFILE_ID
        legacy = base / LEGACY_PROFILE_ID
        if not root.exists() and legacy.is_dir():
            root = legacy
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_downloads() -> Path:
    path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    return Path(path) if path else Path.home() / "Downloads"


def settings_store() -> QSettings:
    executable_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else app_root()
    if (executable_dir / "portable.flag").exists():
        return QSettings(str(data_root() / "settings.ini"), QSettings.Format.IniFormat)
    settings = QSettings("AnyLoadMedia", PROFILE_ID)
    legacy = QSettings(LEGACY_PROFILE_ID, LEGACY_PROFILE_ID)
    return legacy if not settings.allKeys() and legacy.allKeys() else settings


@dataclass
class Preferences:
    folder: str = ""
    concurrency: int = 3
    theme: str = "dark"
    language: str = "ru"
    media_mode: str = "video"
    audio_format: str = "mp3"
    mp3_bitrate: int = 320
    video_quality: str = "best"
    name_style: str = "title"
    subfolders: str = "none"
    music_tags: bool = True
    music_cover: bool = True
    close_to_tray: bool = False
    config_revision: int = 6

    @classmethod
    def load(cls) -> Preferences:
        settings = settings_store()
        result = cls()
        for key in asdict(result):
            default = getattr(result, key)
            try:
                value = settings.value(key, default, type=type(default))
            except (TypeError, ValueError):
                value = default
            setattr(result, key, value)
        result.folder = result.folder or str(default_downloads())
        result.concurrency = max(1, min(5, result.concurrency))
        if not settings.contains("config_revision") and result.concurrency == 2:
            result.concurrency = 3
        result.config_revision = 6
        result.theme = result.theme if result.theme in {"dark", "light", "system"} else "dark"
        result.language = result.language if result.language in {"ru", "en", "be", "uk"} else "ru"
        result.media_mode = result.media_mode if result.media_mode in {"video", "audio"} else "video"
        result.audio_format = result.audio_format if result.audio_format in {"audio", "mp3", "m4a"} else "mp3"
        result.mp3_bitrate = result.mp3_bitrate if result.mp3_bitrate in {128, 192, 320} else 320
        result.name_style = result.name_style if result.name_style in {"title", "artist_title"} else "title"
        result.subfolders = result.subfolders if result.subfolders in {"none", "source", "author", "playlist"} else "none"
        if result.video_quality != "best" and not (result.video_quality.startswith("video:") and result.video_quality.split(":")[1].isdigit() and int(result.video_quality.split(":")[1]) > 0):
            result.video_quality = "best"
        return result

    def save(self) -> None:
        settings = settings_store()
        for key, value in asdict(self).items():
            settings.setValue(key, value)
        settings.sync()
        if settings.status() != QSettings.Status.NoError:
            raise OSError("Could not save settings")


def validate_folder(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir() or not os.access(path, os.W_OK):
        raise OSError(f"Folder is not writable: {path}")
    return path
