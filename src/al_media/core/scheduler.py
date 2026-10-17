from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from PySide6.QtCore import QObject, Signal

from al_media.config import Preferences, validate_folder
from al_media.database import Database
from al_media.models import State, Task

from .engine import EngineJob
from .metadata import available_selections


class Scheduler(QObject):
    changed = Signal(object)
    removed = Signal(str)

    def __init__(self, database: Database, tools: dict[str, Path], preferences: Preferences,
                 parent: QObject | None = None):
        super().__init__(parent)
        self.database = database
        self.tools = tools
        self.preferences = preferences
        self.tasks = {task.id: task for task in database.all()}
        self.jobs: dict[str, EngineJob] = {}
        self.stopping = False

    def _save(self, task: Task) -> None:
        self.database.save(task)
        self.changed.emit(task)

    def add(self, url: str, *, download: bool = False) -> Task:
        task = Task(url=url, folder=self.preferences.folder)
        parsed = urlsplit(url)
        playlist_link = parsed.path.rstrip("/") == "/playlist" and bool(parse_qs(parsed.query).get("list"))
        if download and not playlist_link:
            task.state = State.READY
        self.tasks[task.id] = task
        self._save(task)
        if task.state == State.READY:
            self.enqueue(task.id)
        else:
            self.fetch(task.id)
        return task

    def fetch(self, task_id: str) -> None:
        task = self.tasks[task_id]
        if task_id in self.jobs or self.stopping:
            return
        if task.state in {State.FAILED, State.CANCELLED, State.INTERRUPTED}:
            task.transition(State.PENDING_METADATA)
        if task.state != State.PENDING_METADATA:
            return
        task.error = ""
        task.percent = task.downloaded = task.total = task.speed = task.eta = None
        self._save(task)
        self.pump()

    def _start_job(self, task: Task, mode: str) -> None:
        job = EngineJob(task, self.tools, self.preferences, mode, self)
        self.jobs[task.id] = job
        job.metadata_ready.connect(self._metadata)
        job.details_ready.connect(self._details)
        job.notice.connect(self._notice)
        job.progress.connect(self._progress)
        job.completed.connect(self._completed)
        job.failed.connect(self._failed)
        job.finished.connect(self._job_finished)
        job.start()

    def _details(self, task_id: str, info: dict) -> None:
        """Fill a direct download card without a separate extraction request."""
        task = self.tasks[task_id]
        task.title = str(info.get("title") or info.get("id") or task.title)
        task.source = str(info.get("extractor_key") or task.source)
        task.author = str(info.get("uploader") or "")
        duration = info.get("duration")
        task.duration = float(duration) if isinstance(duration, (int, float)) else None
        self._save(task)

    def _notice(self, task_id: str, message: str) -> None:
        task = self.tasks[task_id]
        task.error = message
        self._save(task)

    def _metadata(self, task_id: str, info: dict) -> None:
        task = self.tasks[task_id]
        task.title = str(info.get("title") or info.get("id") or "Untitled")
        task.source = str(info.get("extractor_key") or info.get("extractor") or "")
        task.author = str(info.get("uploader") or info.get("channel") or "")
        task.thumbnail = str(info.get("thumbnail") or "")
        duration = info.get("duration")
        task.duration = float(duration) if isinstance(duration, (int, float)) else None
        raw_formats = info.get("formats")
        task.formats = [item for item in raw_formats if isinstance(item, dict)] if isinstance(raw_formats, list) else []
        raw_entries = info.get("entries")
        entries = raw_entries if isinstance(raw_entries, list) else []
        task.playlist_count = len(entries) if entries else None
        task.playlist = info.get("_type") == "playlist" and bool(entries)
        if entries and isinstance(entries[0], dict):
            first = entries[0].get("webpage_url") or entries[0].get("url") or ""
            task.playlist_first_url = first if isinstance(first, str) and first.startswith(("http://", "https://")) else ""
        choices = available_selections(info)
        if not task.playlist and not choices:
            task.error = "error_no_formats"
            task.transition(State.FAILED)
        else:
            if not task.playlist and task.selection not in {key for key, _ in choices}:
                lower = [key for key, _ in choices if key.startswith("video:") and task.selection.startswith("video:")
                         and int(key.split(":")[1]) <= int(task.selection.split(":")[1])]
                task.selection = lower[0] if lower else choices[0][0]
            task.transition(State.READY)
        self._save(task)

    def enqueue(self, task_id: str) -> None:
        task = self.tasks[task_id]
        if task.state not in {State.READY, State.FAILED, State.CANCELLED, State.INTERRUPTED}:
            return
        try:
            task.folder = str(validate_folder(task.folder or self.preferences.folder))
        except OSError:
            task.error = "error_folder_unavailable"
            if task.state != State.FAILED:
                task.state = State.FAILED
            self._save(task)
            return
        task.error = ""
        task.percent = task.downloaded = task.total = task.speed = task.eta = None
        task.transition(State.QUEUED)
        self._save(task)
        self.pump()

    def pump(self) -> None:
        if self.stopping:
            return
        active = sum(task.state in {State.DOWNLOADING, State.POSTPROCESSING}
                     for task in self.tasks.values())
        for task in list(self.tasks.values()):
            if active >= self.preferences.concurrency:
                break
            if task.state == State.QUEUED and task.id not in self.jobs:
                task.transition(State.DOWNLOADING)
                self._save(task)
                self._start_job(task, "download")
                active += 1
        metadata_active = sum(task.state == State.FETCHING_METADATA for task in self.tasks.values())
        for task in list(self.tasks.values()):
            if metadata_active >= min(2, self.preferences.concurrency):
                break
            if task.state == State.PENDING_METADATA and task.id not in self.jobs:
                task.transition(State.FETCHING_METADATA)
                self._save(task)
                self._start_job(task, "metadata")
                metadata_active += 1

    def _progress(self, task_id: str, progress: object) -> None:
        task = self.tasks[task_id]
        task.error = ""
        if progress.stage == "postprocess" and task.state == State.DOWNLOADING:
            task.transition(State.POSTPROCESSING)
        task.percent = progress.percent
        task.downloaded = progress.downloaded
        task.total = progress.total
        task.speed = progress.speed
        task.eta = progress.eta
        self._save(task)

    def _completed(self, task_id: str, files: list[str]) -> None:
        task = self.tasks[task_id]
        task.final_path = files[0]
        task.final_paths = files
        if task.playlist_count and task.playlist and len(files) < task.playlist_count:
            task.error = f"Only {len(files)} of {task.playlist_count} playlist files were produced"
            task.transition(State.FAILED)
            self._save(task)
            return
        task.transition(State.COMPLETED)
        task.percent = 100
        self._save(task)

    def _failed(self, task_id: str, error_code: str) -> None:
        task = self.tasks[task_id]
        task.error = error_code
        task.transition(State.CANCELLED if error_code == "cancelled" else State.FAILED)
        self._save(task)

    def _job_finished(self, task_id: str) -> None:
        job = self.jobs.pop(task_id, None)
        if job:
            job.deleteLater()
        self.pump()

    def cancel(self, task_id: str) -> None:
        task = self.tasks[task_id]
        if task_id in self.jobs:
            self.jobs[task_id].cancel()
        elif task.state in {State.PENDING_METADATA, State.READY, State.QUEUED}:
            task.transition(State.CANCELLED)
            self._save(task)
            self.pump()

    def remove(self, task_id: str) -> None:
        if task_id in self.jobs:
            return
        task = self.tasks[task_id]
        if task.state == State.COMPLETED:
            task.hidden = True
            self.database.save(task)
        else:
            self.database.remove(task_id)
            del self.tasks[task_id]
        self.removed.emit(task_id)

    def shutdown(self) -> None:
        self.stopping = True
        for task in self.tasks.values():
            if task.state in {State.PENDING_METADATA, State.QUEUED}:
                task.transition(State.CANCELLED)
                self._save(task)
        for job in list(self.jobs.values()):
            job.cancel()

    def cancel_all(self) -> None:
        self.stopping = True
        try:
            for task in list(self.tasks.values()):
                self.cancel(task.id)
        finally:
            self.stopping = False
