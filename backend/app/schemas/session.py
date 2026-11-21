from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SessionStatus = Literal["active", "paused", "stopped"]


class Session(BaseModel):
    id: str
    title: str
    status: SessionStatus
    started_at: str
    ended_at: str | None = None


class StartSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class Suggestion(BaseModel):
    id: str
    session_id: str | None
    prompt: str
    response: str
    status: Literal["streaming", "done", "error"]
    created_at: str
    auto: bool = False


class TranscriptSegment(BaseModel):
    id: int
    session_id: str
    speaker: Literal["interviewer", "user", "unknown", "screen"]
    text: str
    created_at: str
    is_question: bool = False


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)


class SessionDetail(Session):
    suggestions: list[Suggestion] = []
    transcript: list[TranscriptSegment] = []
