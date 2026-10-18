from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, APP_USER_MODEL_ID, __version__
from .config import Preferences, app_root, data_root
from .core.scheduler import Scheduler
from .core.tools import bundled_tools
from .database import Database
from .ui.main_window import MainWindow


def run() -> int:
    smoke_gui = "--smoke-gui" in sys.argv
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    app = QApplication(sys.argv)
    font = QFont("Segoe UI")
    font.setPixelSize(13)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferQuality)
    app.setFont(font)
    app.setOrganizationName("AnyLoadMedia")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(app_root() / "assets" / "app.ico")))
    # A packaged startup check must never interrupt the user's saved queue or
    # acquire its profile lock. Keep all smoke-test data in a temporary profile.
    smoke_profile = TemporaryDirectory(prefix="al-media-smoke-") if smoke_gui else None
    profile_root = Path(smoke_profile.name) if smoke_profile else data_root()
    preferences = Preferences(folder=str(profile_root / "downloads")) if smoke_gui else Preferences.load()
    lock = QLockFile(str(profile_root / "app.lock"))
    lock.setStaleLockTime(0)
    if not smoke_gui and not lock.tryLock(0):
        QMessageBox.information(None, APP_NAME, "Приложение уже открыто. Переключитесь на его окно.")
        return 0
    log_dir = profile_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    try:
        database = Database(profile_root / "data" / "app.sqlite3")
    except Exception as exc:
        QMessageBox.critical(None, "Database / База данных", f"Cannot open history / Не удалось открыть историю: {type(exc).__name__}")
        return 1
    scheduler = Scheduler(database, bundled_tools(), preferences)
    window = MainWindow(scheduler, preferences, probe_tools=not smoke_gui)
    window.showMaximized()
    if smoke_gui:
        QTimer.singleShot(500, app.quit)
    result = app.exec()
    database.close()
    if not smoke_gui:
        lock.unlock()
    if smoke_profile:
        logging.shutdown()
        smoke_profile.cleanup()
    return result
