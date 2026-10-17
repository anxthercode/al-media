from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass
class Progress:
    stage: str
    downloaded: int | None = None
    total: int | None = None
    speed: float | None = None
    eta: float | None = None
    percent: float | None = None


def _number(value: str) -> float | None:
    try:
        result = float(value.strip().replace("%", ""))
        return result if isfinite(result) else None
    except (ValueError, TypeError):
        return None


def parse_progress(line: str) -> Progress | None:
    if not line.startswith("ALM_PROGRESS:"):
        return None
    fields = line.removeprefix("ALM_PROGRESS:").split("|")
    if len(fields) != 7 or fields[0] not in {"download", "postprocess"}:
        return None
    downloaded = _number(fields[1])
    total = _number(fields[2]) or _number(fields[3])
    speed = _number(fields[4])
    eta = _number(fields[5])
    percent = _number(fields[6])
    if percent is None and downloaded is not None and total:
        percent = downloaded / total * 100
    return Progress(fields[0], int(downloaded) if downloaded is not None else None,
                    int(total) if total is not None else None, speed, eta, percent)


class LineBuffer:
    def __init__(self) -> None:
        self.pending = ""

    def feed(self, text: str) -> list[str]:
        self.pending += text.replace("\r", "\n")
        pieces = self.pending.split("\n")
        self.pending = pieces.pop()
        return pieces

    def flush(self) -> list[str]:
        value, self.pending = self.pending, ""
        return [value] if value else []
