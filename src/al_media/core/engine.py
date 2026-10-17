from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from al_media.config import Preferences
from al_media.models import Task

from .commands import download_args, metadata_args
from .errors import classify_engine_error
from .progress import LineBuffer, parse_progress


class EngineJob(QObject):
    metadata_ready = Signal(str, dict)
    details_ready = Signal(str, dict)
    notice = Signal(str, str)
    progress = Signal(str, object)
    completed = Signal(str, list)
    failed = Signal(str, str)
    finished = Signal(str)

    def __init__(self, task: Task, tools: dict[str, Path], preferences: Preferences,
                 mode: str, parent: QObject | None = None):
        super().__init__(parent)
        self.task = task
        self.mode = mode
        self.process = QProcess(self)
        self.process.setProgram(str(tools["yt-dlp"]))
        self.process.setArguments(metadata_args(task.url, tools, preferences, task.playlist)
                                  if mode == "metadata" else download_args(task, tools, preferences))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.buffers = {"out": LineBuffer(), "err": LineBuffer()}
        self.stdout: list[str] = []
        self.errors: list[str] = []
        self.files: list[str] = []
        self.cancelled = False
        self._done = False
        self.attempt = 0
        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self._launch)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.process.readyReadStandardOutput.connect(lambda: self._read("out"))
        self.process.readyReadStandardError.connect(lambda: self._read("err"))
        self.process.finished.connect(self._finish)
        self.process.errorOccurred.connect(self._process_error)

    def start(self) -> None:
        self._launch()

    def _launch(self) -> None:
        if self._done or self.cancelled:
            return
        self.attempt += 1
        self.stdout.clear()
        self.errors.clear()
        self.buffers = {"out": LineBuffer(), "err": LineBuffer()}
        self.process.start()
        self.timer.start(90000 if self.mode == "metadata" else 300000)

    def cancel(self) -> None:
        if self._done:
            return
        self.cancelled = True
        self.timer.stop()
        self.retry_timer.stop()
        pid = self.process.processId()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            if os.name == "nt" and pid:
                subprocess.Popen(["taskkill", "/PID", str(pid), "/T", "/F"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
                QTimer.singleShot(2000, self._kill_if_running)
            else:
                self.process.kill()
        else:
            self._finish(0, QProcess.ExitStatus.NormalExit)

    def _kill_if_running(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _timeout(self) -> None:
        if self.mode == "metadata":
            self.errors.append("timed out")
        else:
            self.errors.append("network timed out")
        self.cancel()
        self.cancelled = False

    def _process_error(self, _error: QProcess.ProcessError) -> None:
        if _error == QProcess.ProcessError.FailedToStart and not self._done:
            self._done = True
            self.timer.stop()
            self.failed.emit(self.task.id, "error_engine_missing")
            self.finished.emit(self.task.id)

    def _read(self, channel: str) -> None:
        data = (self.process.readAllStandardOutput() if channel == "out"
                else self.process.readAllStandardError()).data().decode("utf-8", "replace")
        for line in self.buffers[channel].feed(data):
            self._line(channel, line)

    def _line(self, channel: str, line: str) -> None:
        if self.mode == "metadata":
            if channel == "out":
                self.stdout.append(line)
            else:
                self.errors.append(line)
            return
        progress = parse_progress(line)
        if progress:
            self.timer.start(300000)
            self.progress.emit(self.task.id, progress)
        elif line.startswith("ALM_FILE:"):
            value = line.removeprefix("ALM_FILE:")
            try:
                path = json.loads(value) if value.startswith('"') else value
                if isinstance(path, str):
                    self.files.append(path)
            except ValueError:
                pass
        elif line.startswith("ALM_INFO:"):
            try:
                info = json.loads(line.removeprefix("ALM_INFO:"))
                if isinstance(info, dict):
                    self.details_ready.emit(self.task.id, info)
            except ValueError:
                pass
        elif channel == "err":
            self.errors.append(line)

    def _finish(self, code: int, _status: QProcess.ExitStatus) -> None:
        if self._done:
            return
        self.timer.stop()
        self._read("out")
        self._read("err")
        for channel, buffer in self.buffers.items():
            for line in buffer.flush():
                self._line(channel, line)
        self.timer.stop()
        error_code = classify_engine_error(self.errors) if code else ""
        # Like the reference implementation, re-extract an expired media URL.
        # Never loop on a bot challenge, authentication failure or HTTP 429.
        if (not self.cancelled and code != 0 and self.mode == "download" and self.attempt < 2
                and error_code in {"error_media_forbidden", "error_network"}):
            self.notice.emit(self.task.id, "retry_connection")
            self.retry_timer.start(3000)
            return
        self._done = True
        if self.cancelled:
            self.failed.emit(self.task.id, "cancelled")
        elif code != 0:
            logging.getLogger(__name__).warning("Engine job %s failed: %s", self.task.id, error_code)
            self.failed.emit(self.task.id, error_code)
        elif self.mode == "metadata":
            try:
                info = json.loads("\n".join(self.stdout))
                if not isinstance(info, dict):
                    raise ValueError("Metadata is not an object")
                self.metadata_ready.emit(self.task.id, info)
            except (ValueError, json.JSONDecodeError):
                self.failed.emit(self.task.id, "error_invalid_metadata")
        else:
            try:
                folder = Path(self.task.folder).resolve()
                paths = list(dict.fromkeys(Path(name).resolve() for name in self.files))
                valid = [str(path) for path in paths if path.is_file() and path.is_relative_to(folder)]
            except (OSError, ValueError):
                valid = []
                paths = []
            if paths and len(valid) == len(paths):
                self.completed.emit(self.task.id, valid)
            else:
                self.failed.emit(self.task.id, "error_final_file_missing")
        self.finished.emit(self.task.id)
