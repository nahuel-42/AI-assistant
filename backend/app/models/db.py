"""SQLite connection and schema. Stdlib ``sqlite3`` keeps the dependency list short."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL,           -- active | paused | stopped
    started_at  TEXT NOT NULL,
    ended_at    TEXT
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    speaker     TEXT NOT NULL,           -- interviewer | user | unknown
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preferences (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suggestions (
    id          TEXT PRIMARY KEY,
    session_id  TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    prompt      TEXT NOT NULL,
    response    TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL,           -- streaming | done | error
    created_at  TEXT NOT NULL
);
"""


class Database:
    """A single shared connection guarded by a lock; enough for a local single-user app."""

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._lock = threading.Lock()

    def _migrate(self) -> None:
        """Additive column migrations for databases created by earlier versions."""
        wanted = {
            "transcript_segments": {"is_question": "INTEGER NOT NULL DEFAULT 0"},
            "suggestions": {"auto": "INTEGER NOT NULL DEFAULT 0"},
        }
        for table, columns in wanted.items():
            existing = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
            for name, ddl in columns.items():
                if name not in existing:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        self._conn.close()
