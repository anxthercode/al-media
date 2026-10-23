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
    thumbnail_candidates: list[str] = field(default_factory=list)
    formats: list[dict] = field(default_factory=list)
    selection: str = "best"
    playlist: bool = False
    playlist_count: int | None = None
    playlist_first_url: str = ""
    folder: str = ""
    final_path: str = ""
    final_paths: list[str] = field(default_factory=list)
    final_size: int | None = None
    hidden: bool = False
    error: str = ""
    percent: float | None = None
    downloaded: int | None = None
    total: int | None = None
    speed: float | None = None
    eta: float | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    media_id: str = ""
    estimated_size: int | None = None
    subtitles: dict = field(default_factory=dict)
    automatic_captions: dict = field(default_factory=dict)
    audio_languages: list[str] = field(default_factory=list)
    playlist_entries: list[dict] = field(default_factory=list)
    playlist_title: str = ""
    playlist_index: int | None = None
    clip_start: float | None = None
    clip_end: float | None = None
    audio_language: str = ""
    subtitle_language: str = ""
    subtitle_auto: bool = False
    subtitle_mode: str = "none"
    processing_stage: str = ""
    repeat: bool = False
    output_stem: str = ""
    folder_configured: bool = False
    naming_version: int = 2
    auto_start: bool = False
    output_bitrate: int | None = None
    audio_tracks: list[dict] = field(default_factory=list)
    audio_track_ids: list[str] = field(default_factory=list)
    preferences_snapshot: dict = field(default_factory=dict)

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
        if "naming_version" not in value:
            data["naming_version"] = 1
            data["folder_configured"] = True
        if isinstance(data.get("error"), str) and data["error"].startswith("Access requires authorization"):
            data["error"] = "error_auth_required"
        return cls(**data)
