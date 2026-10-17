from al_media.database import Database
from al_media.models import State, Task


def test_persistence_and_interrupted(tmp_path):
    path = tmp_path / 'дата' / 'app.sqlite3'
    db = Database(path)
    task = Task('https://example.test/a', state=State.DOWNLOADING)
    db.save(task)
    db.close()
    db = Database(path)
    assert db.all()[0].state == State.INTERRUPTED
    db.remove(task.id)
    assert not db.all()
    db.close()


def test_waiting_tasks_can_be_retried_after_restart(tmp_path):
    path = tmp_path / 'restart.sqlite3'
    db = Database(path)
    for state in (State.QUEUED, State.PENDING_METADATA):
        db.save(Task('https://example.test/a', state=state))
    db.close()
    db = Database(path)
    assert all(task.state == State.INTERRUPTED for task in db.all())
    db.close()
