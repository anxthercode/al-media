from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from al_media.config import Preferences, validate_folder
from al_media.database import Database
from al_media.models import State, Task

from .engine import EngineJob
from .metadata import available_selections, populate_task, preferred_selection
from .naming import canonical_url, configure_destination, same_result


class Scheduler(QObject):
    changed = Signal(object)
    removed = Signal(str)
    queue_finished = Signal(int, int)

    def __init__(self, database: Database, tools: dict[str, Path], preferences: Preferences,
                 parent: QObject | None = None):
        super().__init__(parent)
        self.database = database
        self.tools = tools
        self.preferences = preferences
        self.tasks = {task.id: task for task in database.all()}
        self.jobs: dict[str, EngineJob] = {}
        self.stopping = False
        self.batch_ids: set[str] = set()

    def _save(self, task: Task) -> None:
        self.database.save(task)
        self.changed.emit(task)

    def add(self, url: str, *, download: bool = False) -> Task:
        selection = self.preferences.video_quality if self.preferences.media_mode == "video" else (
            f"mp3:{self.preferences.mp3_bitrate}" if self.preferences.audio_format == "mp3" else self.preferences.audio_format)
        task = Task(url=url, folder=self.preferences.folder, selection=selection, auto_start=download)
        for existing in self.tasks.values():
            active_states = {State.PENDING_METADATA, State.FETCHING_METADATA, State.READY, State.QUEUED, State.DOWNLOADING, State.POSTPROCESSING}
            if not existing.hidden and canonical_url(existing.url) == canonical_url(url) and existing.selection == selection and existing.state in active_states:
                return existing
        self.tasks[task.id] = task
        self._save(task)
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
        try:
            job = EngineJob(task, self.tools, self.preferences, mode, self)
        except (KeyError, ValueError) as exc:
            task.state = State.FAILED
            task.error = "error_engine_missing" if isinstance(exc, KeyError) else "error_invalid_metadata"
            self._save(task)
            QTimer.singleShot(0, self.pump)
            return
        self.jobs[task.id] = job
        job.metadata_ready.connect(self._metadata)
        job.details_ready.connect(self._details)
        job.notice.connect(self._notice)
        job.progress.connect(self._progress)
        job.stage_changed.connect(self._stage)
        job.output_info.connect(self._output_info)
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

    def _output_info(self, task_id: str, info: dict):
        task = self.tasks[task_id]
        task.output_bitrate = info.get("bitrate")
        self._save(task)

    def _metadata(self, task_id: str, info: dict) -> None:
        task = self.tasks[task_id]
        populate_task(task, info)
        choices = available_selections({"formats": task.formats})
        if not task.playlist and not choices:
            task.error = "error_no_formats"
            task.transition(State.FAILED)
        else:
            if not task.playlist and task.selection not in {key for key, _ in choices}:
                task.selection = preferred_selection(task, self.preferences, task.selection)
            task.transition(State.READY)
        self._save(task)
        if task.state == State.READY and task.auto_start and not task.playlist:
            self.enqueue(task.id)

    def enqueue(self, task_id: str) -> None:
        task = self.tasks[task_id]
        if task.state not in {State.READY, State.FAILED, State.CANCELLED, State.INTERRUPTED}:
            return
        try:
            configure_destination(task, self.preferences)
            task.folder = str(validate_folder(task.folder or self.preferences.folder))
        except OSError:
            task.error = "error_folder_unavailable"
            if task.state != State.FAILED:
                task.state = State.FAILED
            self._save(task)
            return
        task.error = ""
        task.processing_stage = ""
        task.output_bitrate = None
        task.percent = task.downloaded = task.total = task.speed = task.eta = None
        task.transition(State.QUEUED)
        self.batch_ids.add(task.id)
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
        task.percent = None if progress.stage == "postprocess" else progress.percent
        task.downloaded = progress.downloaded
        task.total = progress.total
        task.speed = progress.speed
        task.eta = progress.eta
        self._save(task)

    def _stage(self, task_id: str, stage: str) -> None:
        task = self.tasks[task_id]
        task.processing_stage = stage
        if task.state == State.DOWNLOADING:
            task.transition(State.POSTPROCESSING)
        task.percent = task.speed = task.eta = None
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
        if self.stopping and error_code == "cancelled":
            task.state = State.INTERRUPTED
        else:
            task.transition(State.CANCELLED if error_code == "cancelled" else State.FAILED)
        self._save(task)

    def _job_finished(self, task_id: str) -> None:
        job = self.jobs.pop(task_id, None)
        if job:
            job.deleteLater()
        self.pump()
        if self.batch_ids and not self.jobs and not any(task.state == State.QUEUED for task in self.tasks.values()):
            completed = sum(self.tasks[ident].state == State.COMPLETED for ident in self.batch_ids if ident in self.tasks)
            failed = sum(self.tasks[ident].state == State.FAILED for ident in self.batch_ids if ident in self.tasks)
            self.batch_ids.clear()
            if not self.stopping:
                self.queue_finished.emit(completed, failed)

    def find_duplicate(self, task: Task) -> Task | None:
        return next((existing for existing in self.tasks.values() if existing.id != task.id and same_result(existing, task)
                     and (existing.state in {State.READY, State.QUEUED, State.DOWNLOADING, State.POSTPROCESSING}
                          or existing.state == State.COMPLETED and bool(existing.final_path) and Path(existing.final_path).is_file())), None)

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
                task.state = State.INTERRUPTED
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
