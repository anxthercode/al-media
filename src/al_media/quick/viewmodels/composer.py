from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace

from PySide6.QtCore import Property, QObject, QRunnable, QSettings, Qt, QThreadPool, QTimer, Signal, Slot

from al_media.application.submission import SubmissionService
from al_media.config import Preferences, settings_store
from al_media.core.commands import youtube_playlist_urls
from al_media.core.engine import EngineJob
from al_media.core.metadata import available_selections, estimate_size, parse_urls, populate_task, preferred_selection, selection_kind, source_choices, task_selections, video_heights
from al_media.core.naming import canonical_url
from al_media.core.options import apply_options, format_time
from al_media.core.source_probe import SourceProbe
from al_media.core.subtitles import subtitle_choices
from al_media.models import State, Task

from ..localization import text


def duration_label(value: float | None) -> str:
    if value is None:
        return "—"
    seconds = round(value)
    return f"{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02}"


def size_label(value: int | float | None, language: str = "ru") -> str:
    if not value:
        return "—"
    units = ("Б", "КБ", "МБ", "ГБ") if language == "ru" else ("B", "KB", "MB", "GB")
    unit = 0
    while value >= 1000 and unit < len(units) - 1:
        value /= 1000
        unit += 1
    return f"{value:.1f} {units[unit]}"


def compatible_choices(task: Task, mode: str, audio_format: str = "mp3") -> list[str]:
    available = {key for key, _ in task_selections(task)}
    return [key for key in source_choices(task, mode, audio_format) if key in available]


class _SelectionSave(QRunnable):
    def __init__(self, values, finished):
        super().__init__()
        self.values, self.finished = values, finished

    def run(self):
        error = ""
        try:
            # Own QSettings instance in the worker; only selection keys are
            # written, so delayed saves cannot overwrite unrelated settings.
            settings = settings_store()
            for key, value in self.values.items():
                settings.setValue(key, value)
            settings.sync()
            if settings.status() != QSettings.Status.NoError:
                raise OSError("Selection settings could not be saved")
        except OSError:
            error = "settings_error"
        self.finished.emit(error)


class ComposerViewModel(QObject):
    changed = Signal()
    source_changed = Signal(object)
    enqueue_requested = Signal(object)
    preferences_updated = Signal()
    _selection_save_finished = Signal(str)

    def __init__(self, scheduler, preferences: Preferences, parent=None, *, persist=True, job_factory=EngineJob):
        super().__init__(parent)
        self.scheduler, self.preferences = scheduler, preferences
        self.persist, self.job_factory = persist, job_factory
        self.submissions = SubmissionService(scheduler)
        self.task: Task | None = None
        self._url, self._phase, self._error = "", "empty", ""
        self._playlist_mode = None
        self._mode = preferences.media_mode
        self._audio_format = preferences.audio_format
        self._range_open = self._clip = False
        self._start = self._end = ""
        self._range_error = ""
        self._applied = (False, "", "")
        self._jobs = set()
        self._job = None
        self._generation = 0
        self._drafts: OrderedDict[str, dict] = OrderedDict()
        self._closing = False
        self._saving = False
        self._pending_save = {}
        self._save_timer = QTimer(self, singleShot=True, interval=200)
        self._save_timer.timeout.connect(self._save_selection)
        self._selection_save_finished.connect(self._saved_selection, Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self, singleShot=True, interval=450)
        self.timer.timeout.connect(self.analyze)
        self.probe = SourceProbe(scheduler.tools.get("ffprobe"), self)
        self.probe.updated.connect(self._probed)

    def _remember(self):
        if not self.task:
            return
        key = canonical_url(self.task.url)
        # Drafts need editable options, not a deep copy of every stream,
        # thumbnail fragment and subtitle URL on each mode/bitrate click.
        options = {field: getattr(self.task, field) for field in
                   ("url", "selection", "clip_start", "clip_end", "audio_language", "subtitle_language", "subtitle_auto", "subtitle_mode")}
        options["audio_track_ids"] = list(self.task.audio_track_ids)
        self._drafts[key] = {"task": options, "clip": self._clip, "start": self._start, "end": self._end, "applied": self._applied, "mode": self._mode, "audio": self._audio_format}
        self._drafts.move_to_end(key)
        while len(self._drafts) > 16:
            self._drafts.popitem(last=False)

    def _cancel(self):
        self.timer.stop()
        self.probe.cancel()
        self._generation += 1
        job, self._job = self._job, None
        if job:
            job.cancel()

    @Property("QVariantMap", notify=changed)
    def state(self):
        task, lang = self.task, self.preferences.language
        options = []
        if task:
            for key in compatible_choices(task, self._mode, self._audio_format):
                label = (
                    (text(lang, "best_available") + (f" · {max(video_heights(task))}p" if video_heights(task) else ""))
                    if key == "best"
                    else (f"{key.split(':')[1]} {text(lang, 'kbps')}" if key.startswith("mp3:") else text(lang, "source_audio") if key == "audio" else key.removeprefix("video:") + "p" if key.startswith("video:") else key.upper())
                )
                options.append({"value": key, "label": label})
        dirty = self._applied != (self._clip, self._start, self._end)
        subtitle_options = [{"value": "", "label": text(lang, "none")}]
        tracks = [{"value": "", "label": text(lang, "automatic")}]
        if task:
            tracks += [{"value": str(index), "label": item["label"] or text(lang, "source_audio")} for index, item in enumerate(task.audio_tracks)]
            if self._mode == "video":
                subtitle_options += [{"value": f"{int(auto)}:{code}", "label": text(lang, "subtitle_" + language) + (" · " + text(lang, "auto_captions") if auto else "")}
                                     for code, auto, language in subtitle_choices(task)]
        from al_media.core.metadata import expected_container

        container = expected_container(task) or text(lang, "source_audio") if task else ""
        keys = {key for key, _ in task_selections(task)} if task else set()
        audio_formats = (
            ([{"value": "mp3", "label": "MP3"}] if "mp3:320" in keys else []) + ([{"value": "audio", "label": text(lang, "source_audio")}] if "audio" in keys else []) + ([{"value": "m4a", "label": "M4A"}] if "m4a" in keys else [])
        )
        estimated = estimate_size(task) if task else None
        return {
            "url": self._url,
            "phase": self._phase,
            "error": self._error,
            "title": task.title if task else "",
            "author": task.author if task else "",
            "source": ("YouTube" if "youtube" in task.source.casefold() else "SoundCloud" if "soundcloud" in task.source.casefold() else task.source) if task else "",
            "duration": (text(lang, "playlist_items") + f": {len(task.playlist_entries)}" if task.playlist else duration_label(task.duration)) if task else "",
            "durationHint": format_time(task.duration) if task else "",
            "thumbnail": task.thumbnail if task else "",
            "mode": self._mode,
            "audioFormat": self._audio_format,
            "audioFormats": audio_formats,
            "options": options,
            "selection": task.selection if task else "",
            "rangeOpen": self._range_open,
            "clip": self._clip,
            "rangeStart": self._start,
            "rangeEnd": self._end,
            "rangeDirty": dirty,
            "rangeError": self._range_error,
            "hasRange": bool(task and (task.clip_start is not None or task.clip_end is not None)),
            "rangeLabel": f"{duration_label(task.clip_start or 0)}–{duration_label(task.clip_end or task.duration)}" if task else "",
            "estimated": size_label(estimated, lang) if estimated else "",
            "container": container,
            "canDownload": self._phase in {"ready", "batch"} and not dirty and not self._range_error and (not task or not task.playlist or any(e["url"] for e in task.playlist_entries)),
            "isPlaylist": bool(task and task.playlist),
            "playlistEntries": task.playlist_entries if task else [],
            "tracks": tracks,
            "subtitles": subtitle_options,
            "hasExtra": len(tracks) > 2 or len(subtitle_options) > 1,
            "track": self._track_key(),
            "subtitle": f"{int(task.subtitle_auto)}:{task.subtitle_language}" if task and task.subtitle_language else "",
            "subtitleMode": "embedded" if task and task.subtitle_language and self._mode == "video" else "none",
            "videoAvailable": bool(task and compatible_choices(task, "video")),
            "audioAvailable": bool(task and compatible_choices(task, "audio")),
        }

    def _track_key(self):
        if self.task:
            for index, track in enumerate(self.task.audio_tracks):
                if self.task.audio_track_ids and track["ids"] == self.task.audio_track_ids:
                    return str(index)
        return ""

    def _normalize_subtitles(self):
        if not self.task:
            return
        language = self.task.subtitle_language.replace("_", "-").split("-")[0].lower()
        choice = next((item for item in subtitle_choices(self.task) if item[2] == language), None) if self._mode == "video" else None
        self.task.subtitle_language = choice[0] if choice else ""
        self.task.subtitle_auto = choice[1] if choice else False
        self.task.subtitle_mode = "embedded" if choice else "none"

    @Slot(str)
    def setUrl(self, value):
        if value == self._url:
            return
        self._remember()
        self._cancel()
        self._url = value
        self._playlist_mode = None
        self.task = None
        self._error = self._range_error = ""
        self._range_open = self._clip = False
        self._start = self._end = ""
        self._applied = (False, "", "")
        valid, invalid = parse_urls(value)
        self._phase = "batch" if len(valid) > 1 and not invalid else "loading" if len(valid) == 1 and not invalid else "empty"
        if invalid and value:
            self._error = "invalid_links"
        if self._phase == "loading" and youtube_playlist_urls(valid[0]):
            self._phase = "choice"
        self.changed.emit()
        self.source_changed.emit(None)
        if self._phase == "loading":
            self.timer.start()

    @Slot()
    def pasted(self):
        # QML invokes this only after paste has updated its text; normal typing
        # keeps the debounce. Enter also analyzes without enqueueing anything.
        if self._phase == "loading":
            self.analyze()

    @Slot()
    def analyze(self):
        valid, invalid = parse_urls(self._url)
        if self._closing or invalid or len(valid) != 1:
            return
        context = youtube_playlist_urls(valid[0])
        if context and self._playlist_mode is None:
            self._phase = "choice"
            self.changed.emit()
            return
        self._cancel()
        generation = self._generation
        task = Task(context[int(self._playlist_mode)] if context else valid[0], folder=self.preferences.folder, playlist=bool(context and self._playlist_mode))
        self._phase, self._error = "loading", ""
        self.changed.emit()
        try:
            job = self.job_factory(task, self.scheduler.tools, replace(self.preferences), "metadata", self)
        except (KeyError, ValueError):
            self._fail("error_engine_missing")
            return
        self._job = job
        self._jobs.add(job)
        job.metadata_ready.connect(lambda _id, info: self._ready(generation, task, info))
        job.failed.connect(lambda _id, error: self._fail(error) if generation == self._generation and error != "cancelled" else None)
        job.finished.connect(lambda _id: self._finished(job))
        job.start()

    @Slot(bool)
    def choosePlaylist(self, playlist):
        if self._phase != "choice":
            return
        self._playlist_mode = playlist
        self.analyze()

    def _ready(self, generation, task, info):
        if self._closing or generation != self._generation:
            return
        populate_task(task, info)
        if not task.playlist and not available_selections({"formats": task.formats}):
            self._fail("error_no_formats")
            return
        task.state = State.READY
        cached = self._drafts.get(canonical_url(task.url))
        if cached:
            old = Task.from_dict(cached["task"])
            self._mode, self._audio_format = cached["mode"], cached["audio"]
            self._clip, self._start, self._end, self._applied = cached["clip"], cached["start"], cached["end"], cached["applied"]
            task.selection = preferred_selection(task, self.preferences, old.selection)
            try:
                apply_options(
                    task,
                    old.clip_start is not None or old.clip_end is not None,
                    format_time(old.clip_start),
                    format_time(old.clip_end),
                    {"language": old.audio_language, "ids": old.audio_track_ids},
                    (old.subtitle_language, old.subtitle_auto) if old.subtitle_language else None,
                    old.subtitle_mode,
                )
            except ValueError:
                self._applied = (False, "", "")
        else:
            task.selection = preferred_selection(task, self.preferences)
            self._mode = "video" if selection_kind(task.selection) == "video" else "audio"
        if self._mode == "audio":
            self._audio_format = "mp3" if task.selection.startswith("mp3:") else task.selection
        self.task = task
        self._normalize_subtitles()
        self._phase, self._error = "ready", ""
        self.changed.emit()
        self.source_changed.emit(task)
        self.probe.start(task)

    def _probed(self, task):
        if task is self.task and not self._closing:
            if task.duration is not None and (task.clip_start is not None and task.clip_start >= task.duration or task.clip_end is not None and task.clip_end > task.duration):
                self._range_error = "clip_invalid"
                self._range_open = True
            self.changed.emit()
            self.source_changed.emit(task)

    def _fail(self, error):
        self._phase, self._error = "error", error
        self.changed.emit()

    def _finished(self, job):
        self._jobs.discard(job)
        if job is self._job:
            self._job = None
        job.deleteLater()

    @Slot(str)
    def setMode(self, mode):
        if not self.task or mode not in {"video", "audio"}:
            return
        choices = compatible_choices(self.task, mode, self._audio_format)
        if not choices:
            return
        self._mode = mode
        wanted = self.preferences.video_quality if mode == "video" else f"mp3:{self.preferences.mp3_bitrate}" if self._audio_format == "mp3" else self._audio_format
        self.select(wanted if wanted in choices else choices[0])

    @Slot(str)
    def setAudioFormat(self, value):
        if value not in {item["value"] for item in self.state["audioFormats"]}:
            return
        self._audio_format = value
        self.setMode("audio")

    @Slot(str)
    def select(self, selection):
        if not self.task or selection not in {key for key, _ in task_selections(self.task)}:
            return
        self.task.selection = selection
        self._mode = "video" if selection_kind(selection) == "video" else "audio"
        self._normalize_subtitles()
        self.preferences.media_mode = self._mode
        if self._mode == "video":
            self.preferences.video_quality = selection
        else:
            self.preferences.audio_format = "mp3" if selection.startswith("mp3:") else selection
            self._audio_format = self.preferences.audio_format
            if selection.startswith("mp3:"):
                self.preferences.mp3_bitrate = int(selection.split(":")[1])
        if self.persist:
            self._pending_save = {key: getattr(self.preferences, key) for key in ("media_mode", "video_quality", "audio_format", "mp3_bitrate")}
            self._save_timer.start()
        self._remember()
        self.changed.emit()
        self.preferences_updated.emit()
        self.source_changed.emit(self.task)

    def _save_selection(self):
        if self._saving or not self._pending_save:
            return
        values, self._pending_save = self._pending_save, {}
        self._saving = True
        QThreadPool.globalInstance().start(_SelectionSave(values, self._selection_save_finished))

    def _saved_selection(self, error):
        self._saving = False
        if error and not self._closing:
            self._error = error
            self.changed.emit()
        elif not error and self._error == "settings_error":
            self._error = ""
            self.changed.emit()
        if self._pending_save:
            self._save_selection()

    @Slot()
    def toggleRange(self):
        self._range_open = not self._range_open
        self.changed.emit()

    @Slot()
    def closeRange(self):
        if self._range_open:
            self._range_open = False
            self.changed.emit()

    @Slot(str, "QVariant")
    def editRange(self, key, value):
        if key == "clip":
            self._clip = bool(value)
        elif key == "start":
            self._start = str(value)
            self._clip = True
        elif key == "end":
            self._end = str(value)
            self._clip = True
        self._range_error = ""
        self._remember()
        self.changed.emit()

    @Slot(result=bool)
    def applyRange(self):
        if not self.task:
            return False
        candidate = Task.from_dict(self.task.to_dict())
        clip = self._clip and bool(self._start.strip() or self._end.strip())
        try:
            apply_options(
                candidate,
                clip,
                self._start,
                self._end,
                {"language": self.task.audio_language, "ids": self.task.audio_track_ids},
                (self.task.subtitle_language, self.task.subtitle_auto) if self.task.subtitle_language else None,
                self.task.subtitle_mode,
            )
        except ValueError:
            self._range_error = "clip_invalid"
            self.changed.emit()
            return False
        # Keep source identity: an in-flight SourceProbe still owns this exact
        # source object. Commit validated options without losing its late facts.
        for key in ("clip_start", "clip_end", "audio_language", "audio_track_ids", "subtitle_language", "subtitle_auto", "subtitle_mode", "selection", "output_stem", "naming_version"):
            setattr(self.task, key, getattr(candidate, key))
        self._clip = clip
        self._applied = (self._clip, self._start, self._end)
        self._range_error = ""
        self._range_open = False
        self._remember()
        self.changed.emit()
        self.source_changed.emit(self.task)
        return True

    @Slot()
    def resetRange(self):
        self._clip = False
        self._start = self._end = ""
        self.applyRange()

    @Slot(str, str)
    def setExtra(self, key, value):
        if not self.task:
            return
        if key == "track":
            track = self.task.audio_tracks[int(value)] if value.isdigit() and int(value) < len(self.task.audio_tracks) else {}
            self.task.audio_language, self.task.audio_track_ids = track.get("language", ""), list(track.get("ids", []))
        elif key == "subtitle":
            if self._mode != "video" or value not in {item["value"] for item in self.state["subtitles"]}:
                return
            parts = value.split(":", 1)
            self.task.subtitle_auto = bool(len(parts) == 2 and parts[0] == "1")
            self.task.subtitle_language = parts[1] if len(parts) == 2 else ""
            self.task.subtitle_mode = "embedded" if value else "none"
        if self.task.selection == "m4a" and "m4a" not in {key for key, _ in task_selections(self.task)}:
            self.task.selection = "audio"
            self._audio_format = "audio"
        self._remember()
        self.changed.emit()

    @Slot()
    def download(self):
        if not self.state["canDownload"]:
            if self.state["rangeDirty"]:
                self._range_open = True
                self.changed.emit()
            return
        valid, invalid = parse_urls(self._url)
        if invalid:
            return
        tasks = (
            [self.submissions.prepare(self.task, self.preferences)]
            if self.task
            else [
                Task(url, selection=self.preferences.video_quality if self.preferences.media_mode == "video" else f"mp3:{self.preferences.mp3_bitrate}" if self.preferences.audio_format == "mp3" else self.preferences.audio_format)
                for url in valid
            ]
        )
        if not self.task:
            tasks = [self.submissions.prepare(task, self.preferences) for task in tasks]
        self.enqueue_requested.emit(tasks)

    @Slot(str)
    def loadTask(self, task_id):
        task = self.scheduler.tasks.get(task_id)
        if not task:
            return
        if not task.formats:
            self.setUrl(task.url)
            self.analyze()
            return
        self._remember()
        self._cancel()
        self.task = self.submissions.prepare(task, self.preferences)
        self._url, self._phase, self._error = task.url, "ready", ""
        self._mode = "video" if selection_kind(task.selection) == "video" else "audio"
        self._normalize_subtitles()
        self._clip = task.clip_start is not None or task.clip_end is not None
        self._start, self._end = format_time(task.clip_start), format_time(task.clip_end)
        self._applied = (self._clip, self._start, self._end)
        self._range_open = False
        self.changed.emit()
        self.source_changed.emit(self.task)

    def shutdown(self):
        self._closing = True
        self._save_timer.stop()
        self._save_selection()
        self._cancel()
        for job in list(self._jobs):
            job.cancel()

    @property
    def busy(self):
        return bool(self._jobs) or self.probe.busy or self._saving or bool(self._pending_save)

    def force_stop(self):
        for job in list(self._jobs):
            if job.process.state() != job.process.ProcessState.NotRunning:
                job.process.kill()
