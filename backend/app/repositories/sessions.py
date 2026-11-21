from __future__ import annotations

from datetime import datetime, timezone

from app.models.db import Database
from app.schemas.session import Session, Suggestion, TranscriptSegment


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SessionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, session_id: str, title: str) -> Session:
        started = now_iso()
        self.db.execute(
            "INSERT INTO sessions (id, title, status, started_at) VALUES (?, ?, 'active', ?)",
            (session_id, title, started),
        )
        return Session(id=session_id, title=title, status="active", started_at=started)

    def set_status(self, session_id: str, status: str) -> None:
        ended = now_iso() if status == "stopped" else None
        self.db.execute(
            "UPDATE sessions SET status = ?, ended_at = COALESCE(?, ended_at) WHERE id = ?",
            (status, ended, session_id),
        )

    def get(self, session_id: str) -> Session | None:
        row = self.db.fetchone("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return Session(**dict(row)) if row else None

    def list(self, limit: int = 50) -> list[Session]:
        rows = self.db.fetchall("SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,))
        return [Session(**dict(r)) for r in rows]

    def delete(self, session_id: str) -> bool:
        return self.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,)).rowcount > 0

    def mark_orphans_stopped(self) -> None:
        """Sessions left active by a crash are closed on startup; capture never resumes silently."""
        self.db.execute(
            "UPDATE sessions SET status = 'stopped', ended_at = COALESCE(ended_at, ?) WHERE status != 'stopped'",
            (now_iso(),),
        )


class SuggestionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, suggestion_id: str, session_id: str | None, prompt: str, auto: bool = False) -> Suggestion:
        created = now_iso()
        self.db.execute(
            "INSERT INTO suggestions (id, session_id, prompt, status, created_at, auto) "
            "VALUES (?, ?, ?, 'streaming', ?, ?)",
            (suggestion_id, session_id, prompt, created, int(auto)),
        )
        return Suggestion(
            id=suggestion_id, session_id=session_id, prompt=prompt, response="",
            status="streaming", created_at=created, auto=auto,
        )

    def finish(self, suggestion_id: str, response: str, status: str) -> None:
        self.db.execute(
            "UPDATE suggestions SET response = ?, status = ? WHERE id = ?", (response, status, suggestion_id)
        )

    def for_session(self, session_id: str) -> list[Suggestion]:
        rows = self.db.fetchall(
            "SELECT * FROM suggestions WHERE session_id = ? ORDER BY created_at", (session_id,)
        )
        return [Suggestion(**{**dict(r), "auto": bool(r["auto"])}) for r in rows]


class TranscriptRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, session_id: str, speaker: str, text: str, is_question: bool) -> TranscriptSegment:
        created = now_iso()
        cur = self.db.execute(
            "INSERT INTO transcript_segments (session_id, speaker, text, created_at, is_question) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, speaker, text, created, int(is_question)),
        )
        return TranscriptSegment(
            id=cur.lastrowid, session_id=session_id, speaker=speaker, text=text,
            created_at=created, is_question=is_question,
        )

    def for_session(self, session_id: str) -> list[TranscriptSegment]:
        rows = self.db.fetchall(
            "SELECT * FROM transcript_segments WHERE session_id = ? ORDER BY id", (session_id,)
        )
        return [TranscriptSegment(**{**dict(r), "is_question": bool(r["is_question"])}) for r in rows]


class PreferenceRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str, default: str) -> str:
        row = self.db.fetchone("SELECT value FROM preferences WHERE key = ?", (key,))
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO preferences (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
