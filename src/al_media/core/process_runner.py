from __future__ import annotations

import os
import subprocess
from threading import Event, Thread

from PySide6.QtCore import QObject, Signal


class ProcessRunner(QObject):
    """Launch and drain a processing tool without blocking the Qt GUI thread.

    Windows may spend hundreds of milliseconds inside CreateProcess. Keeping
    both launch and pipe reads on a Python worker also covers that startup cost.
    Only queued signals cross back into the engine's Qt thread.
    """

    output = Signal(str, bytes)
    finished = Signal(int)

    def __init__(self, arguments, channel, parent=None):
        super().__init__(parent)
        self.arguments, self.channel = arguments, channel
        self.cancelled = Event()
        self.process = None
        self.thread = None

    def start(self):
        self.thread = Thread(target=self._run, daemon=True)
        self.thread.start()

    def wait(self, timeout=3):
        if self.thread:
            self.thread.join(timeout)

    def cancel(self):
        self.cancelled.set()
        process = self.process
        if process:
            try:
                process.kill()
            except OSError:
                pass  # The tool may have exited between the check and kill.

    def _run(self):
        code = 1
        try:
            with subprocess.Popen(self.arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as process:
                self.process = process
                if self.cancelled.is_set():
                    self.cancel()
                while data := process.stdout.read1(16384):
                    self.output.emit(self.channel, data)
                code = process.wait()
        except OSError as exc:
            self.output.emit("err", str(exc).encode("utf-8"))
        finally:
            self.process = None
            self.finished.emit(code)
