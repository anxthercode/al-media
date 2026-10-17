from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import ACTIVE, State, Task


class Database:
    """Single GUI-thread connection; every write is committed before returning."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self.connection.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            self.connection.execute("PRAGMA user_version=1")
            self.connection.commit()
        for task in self.all():
            if task.state in ACTIVE | {State.QUEUED, State.PENDING_METADATA}:
                task.state = task.state.INTERRUPTED
                self.save(task)

    def save(self, task: Task) -> None:
        with self.connection:
            self.connection.execute("INSERT INTO tasks(id,data) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (task.id, json.dumps(task.to_dict(), ensure_ascii=False)))

    def all(self) -> list[Task]:
        rows = self.connection.execute("SELECT data FROM tasks ORDER BY rowid DESC").fetchall()
        return [Task.from_dict(json.loads(row[0])) for row in rows]

    def remove(self, task_id: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def close(self) -> None:
        self.connection.close()
