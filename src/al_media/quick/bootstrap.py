from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .controller import ApplicationController
from .media import IconProvider, PreviewProvider


class QuickApplication:
    """Own the engine, registered services and image providers for one window."""

    def __init__(self, app, scheduler, preferences, *, isolated=False):
        if QQuickStyle.name() != "Basic":
            QQuickStyle.setStyle("Basic")
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(self._warnings)
        self.preview = PreviewProvider()
        root = Path(__file__).parent / "qml"
        self.engine.addImageProvider("icons", IconProvider(root / "icons"))
        self.engine.addImageProvider("preview", self.preview)
        self.controller = ApplicationController(scheduler, preferences, self.preview, persist=not isolated, tray=not isolated)
        self.controller.exitReady.connect(app.quit)
        reduced_motion = False
        if sys.platform == "win32":
            import ctypes

            enabled = ctypes.c_int(1)
            if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
                reduced_motion = not bool(enabled.value)
        family = "Segoe UI Variable" if "Segoe UI Variable" in QFontDatabase.families() else "Segoe UI"
        self.engine.setInitialProperties({"services": self.controller, "reducedMotion": reduced_motion, "uiFontFamily": family})
        self.engine.load(QUrl.fromLocalFile(str(root / "Main.qml")))
        if not self.engine.rootObjects():
            raise RuntimeError("Could not load the Qt Quick interface; see QML diagnostics in the log")
        self.window = self.engine.rootObjects()[0]
        self.controller.window = self.window
        self.window.setProperty("font", app.font())

    def _warnings(self, errors):
        for error in errors:
            message = error.toString()
            self.warnings.append(message)
            logging.error("QML: %s", message)

    def dispose(self):
        self.controller.dispose()
        self.engine.deleteLater()
