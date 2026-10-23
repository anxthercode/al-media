from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from time import monotonic

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
        self.pending_progress: set[str] = set()
        self.progress_saved: dict[str, float] = {}
        self.progress_timer = QTimer(self)
        self.progress_timer.setSingleShot(True)
        self.progress_timer.setInterval(150)
        self.progress_timer.timeout.connect(self._flush_progress)

    def _save(self, task: Task) -> None:
        self.pending_progress.discard(task.id)
        self.database.save(task)
        self.changed.emit(task)

    def add(self, url: str, *, download: bool = False) -> Task:
        selection = self.preferences.video_quality if self.preferences.media_mode == "video" else (
            f"mp3:{self.preferences.mp3_bitrate}" if self.preferences.audio_format == "mp3" else self.preferences.audio_format)
        task = Task(url=url, folder=self.preferences.folder, selection=selection, auto_start=download)
        task.preferences_snapshot = asdict(self.preferences)
        for existing in self.tasks.values():
            active_states = {State.PENDING_METADATA, State.FETCHING_METADATA, State.READY, State.QUEUED, State.DOWNLOADING, State.POSTPROCESSING}
            if not existing.hidden and canonical_url(existing.url) == canonical_url(url) and existing.selection == selection and existing.state in active_states:
                return existing
        self.tasks[task.id] = task
        self._save(task)
        self.fetch(task.id)
        return task

    def submit(self, task: Task, *, preferences: Preferences | None = None) -> Task:
        """Publish a detached composer snapshot through the scheduler's public API.

        Duplicate confirmation belongs to the application layer. Capture destination
        and naming before publishing so subsequent preference edits cannot change it.
        """
        if self.stopping or task.id in self.tasks:
            raise ValueError("Task cannot be submitted")
        task = Task.from_dict(task.to_dict())
        effective = preferences or self.preferences
        task.preferences_snapshot = task.preferences_snapshot or asdict(effective)
        effective = self.preferences_for(task)
        task.folder = task.folder or effective.folder
        if task.state == State.READY:
            configure_destination(task, effective)
        elif task.state != State.PENDING_METADATA:
            raise ValueError("Only a source or a prepared task can be submitted")
        task.auto_start = True
        self.tasks[task.id] = task
        self._save(task)
        if task.state == State.READY:
            self.enqueue(task.id)
        else:
            self.fetch(task.id)
        return task

    def preferences_for(self, task: Task) -> Preferences:
        values = {key: value for key, value in task.preferences_snapshot.items()
                  if key in Preferences.__dataclass_fields__}
        return replace(self.preferences, **values)

    def retry(self, task_id: str) -> None:
        task = self.tasks[task_id]
        if task.state not in {State.READY, State.FAILED, State.CANCELLED, State.INTERRUPTED}:
            return
        if task.formats and not task.playlist:
            self.enqueue(task_id)
        else:
            task.auto_start = True
            self.fetch(task_id)

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
            job = EngineJob(task, self.tools, self.preferences_for(task), mode, self)
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
                task.selection = preferred_selection(task, self.preferences_for(task), task.selection)
            task.transition(State.READY)
        self._save(task)
        if task.state == State.READY and task.auto_start and not task.playlist:
            self.enqueue(task.id)

    def enqueue(self, task_id: str) -> None:
        task = self.tasks[task_id]
        if task.state not in {State.READY, State.FAILED, State.CANCELLED, State.INTERRUPTED}:
            return
        try:
            configure_destination(task, self.preferences_for(task))
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
        state_changed = progress.stage == "postprocess" and task.state == State.DOWNLOADING
        if state_changed:
            task.transition(State.POSTPROCESSING)
        task.percent = None if progress.stage == "postprocess" else progress.percent
        task.downloaded = progress.downloaded
        task.total = progress.total
        task.speed = progress.speed
        task.eta = progress.eta
        if state_changed:
            self._save(task)
        else:
            self.pending_progress.add(task_id)
            if not self.progress_timer.isActive():
                self.progress_timer.start()

    def _flush_progress(self):
        pending, self.pending_progress = self.pending_progress, set()
        now = monotonic()
        for task_id in pending:
            task = self.tasks.get(task_id)
            if not task or task.state not in {State.DOWNLOADING, State.POSTPROCESSING}:
                continue
            # A progress checkpoint need not rewrite all extraction metadata on
            # every engine line. State transitions still persist immediately.
            if now - self.progress_saved.get(task_id, 0) >= 2:
                self.database.save(task)
                self.progress_saved[task_id] = now
            self.changed.emit(task)

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
        try:
            task.final_size = Path(files[0]).stat().st_size
        except OSError:
            task.final_size = None
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
        self.pending_progress.discard(task_id)
        self.progress_saved.pop(task_id, None)
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
        self.progress_timer.stop()
        self.pending_progress.clear()
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

    def force_stop(self) -> None:
        """Escalate an already requested shutdown without blocking the Qt loop."""
        for job in list(self.jobs.values()):
            if job.process.state() != job.process.ProcessState.NotRunning:
                job.process.kill()
