from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FolderCheck:
    path: str = ""
    state: str = "error"
    error: str = "folder_invalid"
    created: bool = False


def folder_path(value: str) -> Path:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    path = Path(os.path.expandvars(value)).expanduser()
    if not value or not path.is_absolute():
        raise ValueError("An absolute folder path is required")
    if os.name == "nt":
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        for part in path.parts[1:]:
            if part in {".", ".."}:
                continue
            if re.search(r'[<>:"|?*\x00-\x1f]', part) or part.endswith((" ", ".")) or part.split(".")[0].upper() in reserved:
                raise ValueError("Invalid Windows folder name")
    return path


def inspect_folder(value: str, *, create: bool = False) -> FolderCheck:
    """Read-only while typing; create and verify an actual write only on apply."""
    try:
        path = folder_path(value)
        if not Path(path.anchor).is_dir():
            return FolderCheck(error="folder_drive_unavailable")
        path = path.resolve()
        exists = path.exists()
        ancestor = path
        while not ancestor.exists() and ancestor.parent != ancestor:
            ancestor = ancestor.parent
        if not ancestor.is_dir():
            return FolderCheck(error="folder_not_directory")
        if not os.access(ancestor, os.W_OK):
            return FolderCheck(error="folder_denied")
        if create:
            path.mkdir(parents=True, exist_ok=True)
            # os.access alone cannot establish effective Windows ACL access.
            # A private, automatically removed file verifies the real operation.
            with tempfile.TemporaryFile(prefix=".al-media-", dir=path) as probe:
                probe.write(b"\0")
                probe.flush()
        return FolderCheck(str(path), "found" if exists or create else "missing", "", create and not exists)
    except (ValueError, RuntimeError):
        return FolderCheck(error="folder_invalid")
    except PermissionError:
        return FolderCheck(error="folder_denied")
    except OSError as error:
        if getattr(error, "winerror", None) in {87, 123, 206}:
            return FolderCheck(error="folder_invalid")
        return FolderCheck(error="error_folder_unavailable")
