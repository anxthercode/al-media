import sys
from pathlib import Path

from PySide6.QtCore import QProcessEnvironment

from al_media.config import Preferences
from al_media.core.engine import EngineJob
from al_media.core.progress import Progress
from al_media.core.scheduler import Scheduler
from al_media.database import Database
from al_media.models import State, Task

FIXTURE = Path(__file__).parent / "fixtures" / "fake_engine.py"
TOOLS = {name: Path(sys.executable) for name in ("yt-dlp", "ffmpeg", "deno")}


def test_progress_burst_is_coalesced_and_final_state_is_durable(qtbot, tmp_path, monkeypatch):
    db = Database(tmp_path / "progress.sqlite3")
    scheduler = Scheduler(db, TOOLS, Preferences(folder=str(tmp_path)))
    task = Task("https://fixture.test/video", state=State.DOWNLOADING)
    scheduler.tasks[task.id] = task
    writes, updates = [], []
    save = db.save

    def recording_save(task):
        writes.append(task.percent)
        save(task)

    monkeypatch.setattr(db, "save", recording_save)
    scheduler.changed.connect(lambda task: updates.append(task.percent))
    for value in range(1000):
        scheduler._progress(task.id, Progress("download", percent=value / 10))
    assert not writes and not updates
    qtbot.waitUntil(lambda: bool(updates))
    assert writes == [99.9] and updates == [99.9]
    scheduler._completed(task.id, [str(tmp_path / "video.mkv")])
    assert db.all()[0].state == State.COMPLETED and db.all()[0].percent == 100
    db.close()


def _job(task, mode, tmp_path):
    prefs = Preferences(folder=str(tmp_path))
    job = EngineJob(task, TOOLS, prefs, mode)
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert("PYTHONIOENCODING", "utf-8")
    job.process.setProcessEnvironment(environment)
    job.process.setArguments([str(FIXTURE), *job.process.arguments()])
    return job


def test_fake_metadata_and_download(qtbot, tmp_path):
    task = Task("https://fixture.test/video", folder=str(tmp_path))
    info = []
    job = _job(task, "metadata", tmp_path)
    job.metadata_ready.connect(lambda _id, data: info.append(data))
    with qtbot.waitSignal(job.finished, timeout=5000):
        job.start()
    assert info[0]["title"] == "Fixture"
    files = []
    failures = []
    job = _job(task, "download", tmp_path)
    job.completed.connect(lambda _id, paths: files.extend(paths))
    job.failed.connect(lambda _id, error: failures.append(error))
    with qtbot.waitSignal(job.finished, timeout=5000):
        job.start()
    assert files, failures
    assert Path(files[0]).is_file()


def test_scheduler_concurrency(qtbot, tmp_path, monkeypatch):
    db = Database(tmp_path / "db.sqlite3")
    scheduler = Scheduler(db, TOOLS, Preferences(folder=str(tmp_path), concurrency=1))
    started = []
    monkeypatch.setattr(scheduler, "_start_job", lambda task, mode: started.append(task.id))
    for _ in range(3):
        task = Task("https://fixture.test/video", folder=str(tmp_path), state=State.READY)
        scheduler.tasks[task.id] = task
        scheduler.enqueue(task.id)
    assert len(started) == 1
    db.close()


def test_fake_engine_failure(qtbot, tmp_path):
    task = Task("https://failure.test/video", folder=str(tmp_path))
    failures = []
    job = _job(task, "metadata", tmp_path)
    job.failed.connect(lambda _id, error: failures.append(error))
    with qtbot.waitSignal(job.finished, timeout=5000):
        job.start()
    assert failures == ["error_unsupported_url"]


def test_missing_engine_reports_failure_without_crashing(qtbot, tmp_path):
    task = Task("https://fixture.test/video", folder=str(tmp_path))
    tools = {**TOOLS, "yt-dlp": tmp_path / "missing.exe"}
    job = EngineJob(task, tools, Preferences(folder=str(tmp_path)), "metadata")
    failures = []
    job.failed.connect(lambda _id, code: failures.append(code))
    with qtbot.waitSignal(job.finished, timeout=5000):
        job.start()
    assert failures == ["error_engine_missing"]


def test_bot_challenge_does_not_enable_browser_access(qtbot, tmp_path, monkeypatch):
    db = Database(tmp_path / "bot.sqlite3")
    prefs = Preferences(folder=str(tmp_path))
    scheduler = Scheduler(db, TOOLS, prefs)
    original_start = EngineJob.start
    seen_args = []

    def fake_start(job):
        seen_args.append(job.process.arguments())
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        job.process.setProcessEnvironment(environment)
        job.process.setArguments([str(FIXTURE), *job.process.arguments()])
        original_start(job)

    task = Task("https://bot.test/video", folder=str(tmp_path))
    scheduler.tasks[task.id] = task
    scheduler._save(task)
    monkeypatch.setattr(EngineJob, "start", fake_start)
    scheduler.fetch(task.id)
    qtbot.waitUntil(lambda: task.state == State.FAILED and task.id not in scheduler.jobs, timeout=5000)
    assert task.error == "error_youtube_verification"
    assert db.all()[0].error == "error_youtube_verification"
    prefs.cookie_mode = "browser"
    prefs.cookie_browser = "firefox"
    scheduler.fetch(task.id)
    qtbot.waitUntil(lambda: len(seen_args) == 2 and task.state == State.FAILED and task.id not in scheduler.jobs, timeout=5000)
    assert seen_args[0].count("--cookies-from-browser") == 0
    assert "--cookies-from-browser" not in seen_args[1]
    db.close()


def test_scheduler_end_to_end_with_fake_process(qtbot, tmp_path, monkeypatch):
    db = Database(tmp_path / "history.sqlite3")
    scheduler = Scheduler(db, TOOLS, Preferences(folder=str(tmp_path), concurrency=2))
    original_start = EngineJob.start

    def fake_start(job):
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        job.process.setProcessEnvironment(environment)
        job.process.setArguments([str(FIXTURE), *job.process.arguments()])
        original_start(job)

    monkeypatch.setattr(EngineJob, "start", fake_start)
    task = scheduler.add("https://fixture.test/video")
    qtbot.waitUntil(lambda: task.state == State.READY, timeout=5000)
    scheduler.enqueue(task.id)
    qtbot.waitUntil(lambda: task.state == State.COMPLETED, timeout=5000)
    assert task.percent == 100
    assert Path(task.final_path).is_file()
    assert db.all()[0].state == State.COMPLETED
    db.close()


def test_cancel_running_fake_process(qtbot, tmp_path):
    task = Task("https://slow.test/video", folder=str(tmp_path))
    job = _job(task, "download", tmp_path)
    failures = []
    job.failed.connect(lambda _id, error: failures.append(error))
    job.start()
    qtbot.waitUntil(lambda: job.process.processId() > 0, timeout=5000)
    with qtbot.waitSignal(job.finished, timeout=5000):
        job.cancel()
    assert failures == ["cancelled"]


def test_metadata_requests_respect_concurrency(qtbot, tmp_path, monkeypatch):
    db = Database(tmp_path / "metadata-queue.sqlite3")
    scheduler = Scheduler(db, TOOLS, Preferences(folder=str(tmp_path), concurrency=1))
    started = []
    monkeypatch.setattr(scheduler, "_start_job", lambda task, mode: started.append((task.id, mode)))
    tasks = [scheduler.add(f"https://fixture.test/{i}") for i in range(4)]
    assert len(started) == 1
    assert [task.state for task in tasks] == [State.FETCHING_METADATA, *[State.PENDING_METADATA] * 3]
    scheduler.shutdown()
    scheduler._failed(tasks[0].id, "cancelled")
    scheduler._job_finished(tasks[0].id)
    assert len(started) == 1
    assert all(task.state == State.INTERRUPTED for task in tasks)
    db.close()


def test_enqueue_during_metadata_signal_waits_for_process_cleanup(qtbot, tmp_path, monkeypatch):
    db = Database(tmp_path / "race.sqlite3")
    scheduler = Scheduler(db, TOOLS, Preferences(folder=str(tmp_path)))
    task = Task("https://fixture.test/video", folder=str(tmp_path), state=State.READY)
    scheduler.tasks[task.id] = task
    scheduler.jobs[task.id] = object()
    started = []
    monkeypatch.setattr(scheduler, "_start_job", lambda task, mode: started.append(mode))
    scheduler.enqueue(task.id)
    assert started == []
    scheduler.jobs.clear()
    scheduler.pump()
    assert started == ["download"]
    db.close()


def test_default_quality_uses_available_lower_resolution(qtbot, tmp_path):
    db = Database(tmp_path / "quality.sqlite3")
    scheduler = Scheduler(db, TOOLS, Preferences(folder=str(tmp_path)))
    task = Task("https://fixture.test/video", state=State.FETCHING_METADATA, selection="video:1080")
    scheduler.tasks[task.id] = task
    scheduler._metadata(task.id, {"title": "Example", "formats": [{"vcodec": "h264", "height": 720}, {"vcodec": "h264", "height": 2160}]})
    assert task.selection == "video:720"
    db.close()


def test_download_request_analyzes_source_before_starting(qtbot, tmp_path, monkeypatch):
    db = Database(tmp_path / "direct.sqlite3")
    scheduler = Scheduler(db, TOOLS, Preferences(folder=str(tmp_path)))
    modes = []
    monkeypatch.setattr(scheduler, "_start_job", lambda task, mode: modes.append(mode))
    task = scheduler.add("https://example.test/video", download=True)
    assert modes == ["metadata"]
    assert task.state == State.FETCHING_METADATA
    scheduler._metadata(task.id, {"title": "Example", "duration": 12, "formats": [{"height": 2160, "vcodec": "h264", "acodec": "aac"}]})
    assert task.title == "Example"
    assert task.state == State.DOWNLOADING
    assert modes == ["metadata", "download"]
    db.close()
