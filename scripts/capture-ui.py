"""Capture the current native interface with an optional real source URL.

Uses an isolated in-memory profile and never starts a media download.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import monotonic

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from al_media.application.typography import load_font
from al_media.config import Preferences, default_downloads
from al_media.core.scheduler import Scheduler
from al_media.core.tools import bundled_tools
from al_media.database import Database
from al_media.quick.bootstrap import QuickApplication


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="")
    parser.add_argument("--output", type=Path, default=Path("docs/images"))
    parser.add_argument("--diagnostics", type=Path, default=Path("build/qa/documentation"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.diagnostics.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setFont(load_font())
    preferences = Preferences(language="ru", theme="dark", folder=str(default_downloads()))
    db = Database(Path(":memory:"))
    scheduler = Scheduler(db, bundled_tools(), preferences)
    presentation = QuickApplication(app, scheduler, preferences, isolated=True)
    window, controller = presentation.window, presentation.controller
    window.resize(1440, 900)
    window.show()
    QTest.qWait(400)

    def capture(name, destination=args.output):
        QTest.qWait(300)
        assert window.grabWindow().save(str(destination / name))

    capture("downloads.png")
    composer = controller.composer
    result = {"url": args.url, "phase": "empty", "errors": []}
    if args.url:
        composer.setUrl(args.url)
        composer.pasted()
        job = composer._job
        if job:
            job.failed.connect(lambda *_: result["errors"].extend(job.errors))
        capture("loading.png", args.diagnostics)
        deadline = monotonic() + 105
        while composer.state["phase"] == "loading" and monotonic() < deadline:
            QTest.qWait(100)
        result.update(phase=composer.state["phase"], message=composer.state["error"])
        if result["phase"] == "ready":
            deadline = monotonic() + 15
            while not controller.media.source and monotonic() < deadline:
                QTest.qWait(100)
            result["title"] = composer.task.title
            result["preview"] = bool(controller.media.source)
            capture("downloads.png")
        else:
            capture("source-error.png", args.diagnostics)

    for page in ("settings", "about"):
        controller.navigate(page)
        capture(page + ".png")
    result["qmlWarnings"] = presentation.warnings
    (args.diagnostics / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    controller.quit()
    deadline = monotonic() + 10
    while not controller._exit_ready and monotonic() < deadline:
        QTest.qWait(100)
    assert controller._exit_ready, "Background jobs did not stop"
    presentation.dispose()
    db.close()


if __name__ == "__main__":
    main()
