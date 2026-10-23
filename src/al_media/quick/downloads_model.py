from __future__ import annotations

from PySide6.QtCore import Property, QAbstractListModel, QModelIndex, Qt, Signal, Slot

from al_media.core.metadata import selection_kind, video_heights
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
        scheduler.changed.connect(self.update_task)
        scheduler.removed.connect(self.remove_task)

    @Property(int, notify=countChanged)
    def count(self):
        return len(self.ids)

    @Property(int, notify=countChanged)
    def completedCount(self):
        return sum(row["taskState"] == "completed" for row in self._rows.values())

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
            from pathlib import Path

            extension = Path(task.final_path).suffix.lstrip(".").upper()
            if task.output_bitrate:
                quality = f"{round(task.output_bitrate / 1000)} {text(lang, 'kbps')}"
            elif task.selection.startswith("mp3:"):
                quality = task.selection.split(":")[1] + " " + text(lang, "kbps")
            else:
                quality = f"{output_height}p" if output_height and selection_kind(task.selection) == "video" else ""
            metadata = " · ".join(filter(None, (task.source, extension, quality, size_label(task.final_size, lang) if task.final_size else "")))
        busy = task.state in {State.PENDING_METADATA, State.FETCHING_METADATA, State.QUEUED, State.DOWNLOADING, State.POSTPROCESSING}
        detail = " · ".join(filter(None, (size_label(task.speed, lang) + "/s" if task.speed else "", "≈ " + duration_label(task.eta) if task.eta is not None and task.state == State.DOWNLOADING else "")))
        if task.state == State.COMPLETED:
            detail = task.final_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return {
            "taskId": task.id,
            "title": task.title or task.url,
            "metadata": metadata,
            "status": text(lang, task.state.value),
            "taskState": task.state.value,
            "progress": task.percent if task.percent is not None else 0.0,
            "indeterminate": busy and (task.percent is None or task.state != State.DOWNLOADING),
            "detail": detail,
            "error": text(lang, task.error) if task.error else "",
            "canCancel": busy or task.state == State.READY,
            "canRetry": task.state in {State.READY, State.FAILED, State.CANCELLED, State.INTERRUPTED},
            "canOpen": task.state == State.COMPLETED and bool(task.final_path),
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
            return
        old = self._rows[task.id]
        roles = [int(Qt.ItemDataRole.UserRole) + i + 1 for i, key in enumerate(self.ROLES) if old[key] != record[key]]
        self._rows[task.id] = record
        if old["taskState"] != record["taskState"] and "completed" in {old["taskState"], record["taskState"]}:
            self.countChanged.emit()
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

    @Slot()
    def retranslate(self):
        for task in self.scheduler.tasks.values():
            if not task.hidden:
                self.update_task(task)
