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
from .naming import publish_files
from .postprocess import cleanup_subtitle_backups, mp3_encoding_plan, postprocess_plans
from .progress import LineBuffer, parse_progress


class EngineJob(QObject):
    metadata_ready = Signal(str, dict)
    details_ready = Signal(str, dict)
    notice = Signal(str, str)
    progress = Signal(str, object)
    completed = Signal(str, list)
    failed = Signal(str, str)
    finished = Signal(str)
    stage_changed = Signal(str, str)
    output_info = Signal(str, dict)

    def __init__(self, task: Task, tools: dict[str, Path], preferences: Preferences,
                 mode: str, parent: QObject | None = None):
        super().__init__(parent)
        self.task = task
        self.tools = tools
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
        self.post_active = False
        self.post_plans = []
        self.current_plan = None
        self.final_paths = []
        self.post_stdout = []
        self.reencoded_mp3 = set()
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
            self.failed.emit(self.task.id, "error_ffmpeg" if self.post_active else "error_engine_missing")
            self.finished.emit(self.task.id)

    def _read(self, channel: str) -> None:
        data = (self.process.readAllStandardOutput() if channel == "out"
                else self.process.readAllStandardError()).data().decode("utf-8", "replace")
        for line in self.buffers[channel].feed(data):
            self._line(channel, line)

    def _line(self, channel: str, line: str) -> None:
        if self.post_active:
            self.timer.start(300000)
            if channel == "out" and self.current_plan and self.current_plan.program == "ffprobe":
                self.post_stdout.append(line)
            if channel == "err":
                self.errors = [*self.errors[-19:], line]
            return
        if self.mode == "metadata":
            if channel == "out":
                self.stdout.append(line)
            else:
                self.errors.append(line)
            return
        for prefix, stage in (("[Merger]", "merging"), ("[ExtractAudio]", "converting"), ("[EmbedThumbnail]", "tagging"),
                              ("[Metadata]", "tagging"), ("[EmbedSubtitle]", "embedding_subtitles")):
            if line.startswith(prefix):
                self.stage_changed.emit(self.task.id, stage)
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
            if "time=" in line or "frame=" in line:
                self.timer.start(300000)
            self.errors.append(line)

    def _finish(self, code: int, _status: QProcess.ExitStatus) -> None:
        if self._done:
            return
        if self.post_active:
            self._finish_postprocess(code)
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
        if self.cancelled:
            self._done = True
            self.failed.emit(self.task.id, "cancelled")
        elif code != 0:
            self._done = True
            logging.getLogger(__name__).warning("Engine job %s failed: %s", self.task.id, error_code)
            self.failed.emit(self.task.id, error_code)
        elif self.mode == "metadata":
            self._done = True
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
                self.final_paths = valid
                try:
                    self.post_plans = postprocess_plans(self.task, valid)
                except (OSError, ValueError):
                    self._done = True
                    self.failed.emit(self.task.id, "error_ffmpeg")
                    self.finished.emit(self.task.id)
                    return
                if self.post_plans:
                    self.post_active = True
                    QTimer.singleShot(0, self._start_postprocess)
                    return
                self._publish(valid)
            else:
                self._done = True
                self.failed.emit(self.task.id, "error_final_file_missing")
        self.finished.emit(self.task.id)

    def _publish(self, paths):
        self._done = True
        try:
            cleanup_subtitle_backups(self.task, paths)
            final_paths = publish_files(self.task, paths)
        except OSError:
            self.failed.emit(self.task.id, "error_folder_denied")
            return
        self.completed.emit(self.task.id, final_paths)

    def _start_postprocess(self):
        if self._done:
            return
        if self.cancelled:
            self._done = True
            self.failed.emit(self.task.id, "cancelled")
            self.finished.emit(self.task.id)
            return
        if not self.post_plans:
            self._publish(self.final_paths)
            self.finished.emit(self.task.id)
            return
        self.current_plan = self.post_plans.pop(0)
        self.errors.clear()
        self.post_stdout.clear()
        self.buffers = {"out": LineBuffer(), "err": LineBuffer()}
        self.stage_changed.emit(self.task.id, self.current_plan.stage)
        executable = self.tools.get(self.current_plan.program, self.tools["ffmpeg"].with_name(self.current_plan.program + ".exe"))
        self.process.setProgram(str(executable))
        self.process.setArguments(self.current_plan.arguments)
        self.process.start()
        self.timer.start(300000)

    def _finish_postprocess(self, code):
        self.timer.stop()
        self._read("out")
        self._read("err")
        for channel, buffer in self.buffers.items():
            for line in buffer.flush():
                self._line(channel, line)
        plan = self.current_plan
        if plan is None:
            self._done = True
            self.failed.emit(self.task.id, "cancelled" if self.cancelled else "error_ffmpeg")
            self.finished.emit(self.task.id)
            return
        if plan.program == "ffprobe" and not self.cancelled and not code:
            try:
                streams = json.loads("\n".join(self.post_stdout)).get("streams", [])
                rate = int(streams[0].get("bit_rate", 0)) if streams else 0
                requested = int(self.task.selection.split(":")[1])
                if rate > requested * 1000 + 1000:
                    if plan.destination in self.reencoded_mp3:
                        raise ValueError("MP3 bitrate was not applied")
                    self.reencoded_mp3.add(plan.destination)
                    self.post_plans[0:0] = [mp3_encoding_plan(plan.destination, requested), plan]
                else:
                    self.output_info.emit(self.task.id, {"bitrate": rate or None})
            except (ValueError, TypeError, IndexError, AttributeError):
                self._done = True
                self.failed.emit(self.task.id, "error_ffmpeg")
                self.finished.emit(self.task.id)
                return
            QTimer.singleShot(0, self._start_postprocess)
            return
        try:
            if self.cancelled or code or plan.temporary is None or not plan.temporary.is_file() or not plan.temporary.stat().st_size:
                raise OSError("Post-processing failed")
            plan.temporary.replace(plan.destination)
        except OSError:
            self._done = True
            if plan and plan.temporary:
                plan.temporary.unlink(missing_ok=True)
            self.failed.emit(self.task.id, "cancelled" if self.cancelled else "error_ffmpeg")
            self.finished.emit(self.task.id)
            return
        QTimer.singleShot(0, self._start_postprocess)
