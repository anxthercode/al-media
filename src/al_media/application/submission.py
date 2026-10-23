from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from al_media.config import Preferences
from al_media.core.metadata import preferred_selection
from al_media.core.naming import configure_destination
from al_media.core.scheduler import Scheduler
from al_media.models import State, Task


class SubmissionService:
    """Prepare independent jobs; UI confirmation and native dialogs stay outside."""

    def __init__(self, scheduler: Scheduler):
        self.scheduler = scheduler

    def prepare(self, source: Task, preferences: Preferences) -> Task:
        task = Task.from_dict(source.to_dict())
        task.id = uuid4().hex
        task.state = State.READY if task.formats else State.PENDING_METADATA
        task.final_path, task.final_paths = "", []
        task.final_size = None
        task.folder = preferences.folder
        task.folder_configured = False
        task.output_stem = ""
        task.repeat = task.hidden = False
        task.preferences_snapshot = asdict(preferences)
        task.percent = task.downloaded = task.total = task.speed = task.eta = None
        task.error = task.processing_stage = ""
        return task

    def playlist(self, source: Task, indices: list[int], preferences: Preferences) -> list[Task]:
        result = []
        for entry in source.playlist_entries:
            if entry["index"] not in indices or not entry["url"]:
                continue
            task = Task(entry["url"], title=entry["title"], playlist_title=source.title, playlist_index=entry["index"], selection=preferred_selection(source, preferences), folder=preferences.folder, preferences_snapshot=asdict(preferences))
            result.append(task)
        return result

    def commit(self, tasks: list[Task], folder: str, *, repeat: bool = False) -> None:
        for task in tasks:
            task.folder = folder
            task.repeat = repeat
            if task.state == State.READY:
                configure_destination(task, self.scheduler.preferences_for(task))
            self.scheduler.submit(task)
