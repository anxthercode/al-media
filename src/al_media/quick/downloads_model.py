from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QAbstractListModel, QFileSystemWatcher, QModelIndex, Qt, QTimer, Signal, Slot

from al_media.core.metadata import selection_kind, video_heights
from al_media.core.subtitles import subtitle_delay
from al_media.models import State

from .localization import text
from .viewmodels.composer import duration_label, size_label


class DownloadsModel(QAbstractListModel):
    countChanged = Signal()
    ROLES = ("taskId", "title", "metadata", "status", "taskState", "progress", "indeterminate", "detail", "error", "canCancel", "canRetry", "canOpen", "sourceUrl", "destination")

    def __init__(self, scheduler, preferences, parent=None):
        super().__init__(parent)
        self.scheduler, self.preferences = scheduler, preferences
        self.ids = [task.id for task in scheduler.tasks.values() if not task.hidden]
        self._rows = {ident: self._record(scheduler.tasks[ident]) for ident in self.ids}
        self._files = QFileSystemWatcher(self)
        self._file_refresh = QTimer(self, singleShot=True, interval=100)
        self._file_refresh.timeout.connect(self.refreshFiles)
        self._files.directoryChanged.connect(self._files_changed)
        self._watch_outputs()
        scheduler.changed.connect(self.update_task)
        scheduler.removed.connect(self.remove_task)

    @Property(int, notify=countChanged)
    def count(self):
        return len(self.ids)

    @Property(int, notify=countChanged)
    def completedCount(self):
        return sum(row["taskState"] == "completed" for row in self._rows.values())

    @Property(int, notify=countChanged)
    def activeCount(self):
        return sum(row["canCancel"] for row in self._rows.values())

    @Property(int, notify=countChanged)
    def clearableCount(self):
        return sum(row["taskState"] in {"completed", "failed", "cancelled", "interrupted"} for row in self._rows.values())

    def roleNames(self):
        return {int(Qt.ItemDataRole.UserRole) + i + 1: key.encode() for i, key in enumerate(self.ROLES)}

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.ids)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.ids):
            return None
        position = role - int(Qt.ItemDataRole.UserRole) - 1
        return self._rows[self.ids[index.row()]][self.ROLES[position]] if 0 <= position < len(self.ROLES) else None

    def _record(self, task):
        lang = self.preferences.language
        highest = max(video_heights(task), default=0)
        selected_height = task.selection.partition(":")[2]
        output_height = int(selected_height) if task.selection.startswith("video:") and selected_height.isdigit() else highest
        selection = (
            f"{highest}p"
            if task.selection == "best" and highest
            else task.selection.removeprefix("video:") + "p"
            if task.selection.startswith("video:")
            else ("MP3 · " + task.selection.split(":")[1] + " " + text(lang, "kbps") if task.selection.startswith("mp3:") else task.selection.upper())
        )
        metadata = " · ".join(filter(None, (task.source, selection, duration_label(task.duration) if task.clip_start is None and task.duration else "")))
        if task.selection == "best" and not highest:
            metadata = metadata.replace("BEST", text(lang, "video_mode"))
        if task.state == State.COMPLETED:
            extension = Path(task.final_path).suffix.lstrip(".").upper()
            if task.output_bitrate:
                quality = f"{round(task.output_bitrate / 1000)} {text(lang, 'kbps')}"
            elif task.selection.startswith("mp3:"):
                quality = task.selection.split(":")[1] + " " + text(lang, "kbps")
            else:
                quality = f"{output_height}p" if output_height and selection_kind(task.selection) == "video" else ""
            metadata = " · ".join(filter(None, (task.source, extension, quality, size_label(task.final_size, lang) if task.final_size else "")))
        busy = task.state in {State.PENDING_METADATA, State.FETCHING_METADATA, State.QUEUED, State.DOWNLOADING, State.POSTPROCESSING}
        detail = ""
        if task.state == State.DOWNLOADING:
            rate = max(0, task.speed or 0) / 1_000_000
            speed = (f"{rate:.2f}" if rate else "0") + " " + text(lang, "megabytes_per_second")
            detail = speed + (" · ≈ " + duration_label(task.eta) if task.eta is not None else "")
        if task.state == State.COMPLETED:
            detail = task.final_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        can_open = False
        if task.state == State.COMPLETED and task.final_path:
            try:
                can_open = Path(task.final_path).is_file()
            except OSError:
                pass
        status = text(lang, task.state.value)
        if task.state == State.COMPLETED and not can_open:
            status = text(lang, "file_missing")
        elif task.state == State.DOWNLOADING and task.processing_stage == "preparing_subtitles":
            status = text(lang, "preparing_subtitles")
            detail = text(lang, "subtitle_wait") if subtitle_delay(task) == 60 else ""
        elif task.state == State.DOWNLOADING and task.processing_stage != "downloading" and task.percent is None and not task.downloaded and not task.speed:
            status = text(lang, "preparing_download")
        elif task.state == State.POSTPROCESSING:
            stage = task.processing_stage if task.processing_stage in {"merging", "converting", "tagging", "embedding_subtitles", "verifying"} else "finishing"
            status = text(lang, "stage_" + stage)
        return {
            "taskId": task.id,
            "title": task.title or task.url,
            "metadata": metadata,
            "status": status,
            "taskState": task.state.value,
            "progress": task.percent if task.percent is not None else 0.0,
            "indeterminate": task.state in {State.FETCHING_METADATA, State.POSTPROCESSING} or task.state == State.DOWNLOADING and task.percent is None,
            "detail": detail,
            "error": text(lang, task.error) if task.error and task.error != "cancelled" else "",
            "canCancel": busy or task.state == State.READY,
            "canRetry": task.state in {State.READY, State.FAILED, State.CANCELLED, State.INTERRUPTED},
            "canOpen": can_open,
            "sourceUrl": task.url,
            "destination": task.folder,
        }

    def update_task(self, task):
        if task.hidden:
            self.remove_task(task.id)
            return
        record = self._record(task)
        if task.id not in self._rows:
            self.beginInsertRows(QModelIndex(), 0, 0)
            self.ids.insert(0, task.id)
            self._rows[task.id] = record
            self.endInsertRows()
            self.countChanged.emit()
            if task.state == State.COMPLETED:
                self._watch_outputs()
            return
        old = self._rows[task.id]
        roles = [int(Qt.ItemDataRole.UserRole) + i + 1 for i, key in enumerate(self.ROLES) if old[key] != record[key]]
        self._rows[task.id] = record
        if old["taskState"] != record["taskState"]:
            self.countChanged.emit()
            if task.state == State.COMPLETED or old["taskState"] == "completed":
                self._watch_outputs()
        if roles:
            index = self.index(self.ids.index(task.id))
            self.dataChanged.emit(index, index, roles)

    def remove_task(self, ident):
        if ident not in self._rows:
            return
        row = self.ids.index(ident)
        self.beginRemoveRows(QModelIndex(), row, row)
        self.ids.pop(row)
        del self._rows[ident]
        self.endRemoveRows()
        self.countChanged.emit()
        self._watch_outputs()

    def _watch_outputs(self):
        directories = {Path(self.scheduler.tasks[ident].final_path).parent.as_posix() for ident in self.ids
                       if self.scheduler.tasks[ident].state == State.COMPLETED and self.scheduler.tasks[ident].final_path}
        watched = set(self._files.directories())
        if removed := watched - directories:
            self._files.removePaths(list(removed))
        if added := directories - watched:
            self._files.addPaths(list(added))

    @Slot(str)
    def _files_changed(self, _path):
        self._file_refresh.start()

    @Slot()
    def refreshFiles(self):
        for ident in list(self.ids):
            task = self.scheduler.tasks.get(ident)
            if task and task.state == State.COMPLETED:
                self.update_task(task)
        self._watch_outputs()

    @Slot()
    def retranslate(self):
        for task in self.scheduler.tasks.values():
            if not task.hidden:
                self.update_task(task)
