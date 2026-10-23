from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, APP_USER_MODEL_ID, __version__
from .application.typography import load_font
from .config import Preferences, app_root, data_root
from .core.scheduler import Scheduler
from .core.tools import bundled_tools
from .database import Database


def run() -> int:
    """Windows entry point with deterministic profile/resource ownership."""
    from contextlib import ExitStack

    smoke_gui = "--smoke-gui" in sys.argv
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    app = QApplication(sys.argv)
    app.setFont(load_font())
    app.setOrganizationName("AnyLoadMedia")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(app_root() / "assets" / "app.ico")))
    try:
        with ExitStack() as resources:
            smoke_profile = resources.enter_context(TemporaryDirectory(prefix="al-media-smoke-")) if smoke_gui else None
            profile_root = Path(smoke_profile) if smoke_profile else data_root()
            preferences = Preferences(folder=str(profile_root / "downloads")) if smoke_gui else Preferences.load()
            lock = QLockFile(str(profile_root / "app.lock"))
            lock.setStaleLockTime(0)
            if not smoke_gui:
                if not lock.tryLock(0):
                    QMessageBox.information(None, APP_NAME, "Приложение уже открыто. Переключитесь на его окно.")
                    return 0
                resources.callback(lock.unlock)
            log_dir = profile_root / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            handlers = [handler, logging.StreamHandler()] if smoke_gui else [handler]
            logging.basicConfig(level=logging.INFO, handlers=handlers, format="%(asctime)s %(levelname)s %(message)s", force=True)
            resources.callback(logging.shutdown)
            database = Database(profile_root / "data" / "app.sqlite3")
            resources.callback(database.close)
            scheduler = Scheduler(database, bundled_tools(), preferences)
            from .quick.bootstrap import QuickApplication
            presentation = QuickApplication(app, scheduler, preferences, isolated=smoke_gui)
            resources.callback(presentation.dispose)
            window = presentation.window
            window.showMaximized()
            if smoke_gui:
                QTimer.singleShot(100, lambda: presentation.controller.navigate("settings"))
                QTimer.singleShot(200, lambda: presentation.controller.navigate("about"))
                QTimer.singleShot(300, lambda: presentation.controller.navigate("downloads"))
                QTimer.singleShot(600, presentation.controller.quit)
            result = app.exec()
            if smoke_gui and presentation.warnings:
                raise RuntimeError("Qt Quick smoke reported QML warnings")
            return result
    except Exception as exc:
        logging.exception("Application startup or shutdown failed")
        message = "Не удалось запустить AL Media. Проверьте доступ к профилю и файлам приложения.\n" + str(exc)
        if smoke_gui:
            print(message, file=sys.stderr)
        else:
            QMessageBox.critical(None, APP_NAME, message)
        return 1
