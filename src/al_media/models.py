from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class State(StrEnum):
    PENDING_METADATA = "pending_metadata"
    FETCHING_METADATA = "fetching_metadata"
    READY = "ready"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


ACTIVE = {State.FETCHING_METADATA, State.DOWNLOADING, State.POSTPROCESSING}
TRANSITIONS = {
    State.PENDING_METADATA: {State.FETCHING_METADATA, State.CANCELLED},
    State.FETCHING_METADATA: {State.READY, State.FAILED, State.CANCELLED},
    State.READY: {State.QUEUED, State.CANCELLED},
    State.QUEUED: {State.DOWNLOADING, State.CANCELLED},
    State.DOWNLOADING: {State.POSTPROCESSING, State.COMPLETED, State.FAILED, State.CANCELLED},
    State.POSTPROCESSING: {State.COMPLETED, State.FAILED, State.CANCELLED},
    State.COMPLETED: set(),
    State.FAILED: {State.PENDING_METADATA, State.QUEUED},
    State.CANCELLED: {State.PENDING_METADATA, State.QUEUED},
    State.INTERRUPTED: {State.PENDING_METADATA, State.QUEUED},
}


@dataclass
class Task:
    url: str
    id: str = field(default_factory=lambda: uuid4().hex)
    state: State = State.PENDING_METADATA
    title: str = ""
    source: str = ""
    duration: float | None = None
    author: str = ""
    thumbnail: str = ""
    formats: list[dict] = field(default_factory=list)
    selection: str = "best"
    playlist: bool = False
    playlist_count: int | None = None
    playlist_first_url: str = ""
    folder: str = ""
    final_path: str = ""
    final_paths: list[str] = field(default_factory=list)
    hidden: bool = False
    error: str = ""
    percent: float | None = None
    downloaded: int | None = None
    total: int | None = None
    speed: float | None = None
    eta: float | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def transition(self, target: State) -> None:
        if target not in TRANSITIONS[self.state]:
            raise ValueError(f"Invalid task transition: {self.state} -> {target}")
        self.state = target

    def to_dict(self) -> dict:
        value = asdict(self)
        value["state"] = self.state.value
        return value

    @classmethod
    def from_dict(cls, value: dict) -> Task:
        known = cls.__dataclass_fields__
        data = {key: State(item) if key == "state" else item
                for key, item in value.items() if key in known}
        if isinstance(data.get("error"), str) and data["error"].startswith("Access requires authorization"):
            data["error"] = "error_auth_required"
        return cls(**data)
