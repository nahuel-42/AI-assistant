from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from app.schemas.session import AskRequest, Session, SessionDetail, StartSessionRequest, Suggestion
from app.services.session_manager import SessionError, SessionManager

router = APIRouter()


def _manager(request: Request) -> SessionManager:
    return request.app.state.manager


def _conflict(exc: SessionError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/api/health")
def health(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "provider": request.app.state.manager.provider.name,
        "audio": settings.audio_enabled,
        "stt_model": settings.stt_model if settings.audio_enabled else None,
    }


@router.get("/api/sessions/current", response_model=Session | None)
def current_session(request: Request) -> Session | None:
    return _manager(request).current


@router.post("/api/sessions", response_model=Session, status_code=201)
async def start_session(body: StartSessionRequest, request: Request) -> Session:
    try:
        return await _manager(request).start(body.title)
    except SessionError as exc:
        raise _conflict(exc) from exc


@router.post("/api/sessions/current/{action}", response_model=Session)
async def control_session(action: str, request: Request) -> Session:
    manager = _manager(request)
    handlers = {"pause": manager.pause, "resume": manager.resume, "stop": manager.stop}
    if action not in handlers:
        raise HTTPException(status_code=404, detail=f"Unknown action {action!r}")
    try:
        return await handlers[action]()
    except SessionError as exc:
        raise _conflict(exc) from exc


@router.get("/api/sessions", response_model=list[Session])
def list_sessions(request: Request) -> list[Session]:
    return _manager(request).sessions.list()


@router.get("/api/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, request: Request) -> SessionDetail:
    manager = _manager(request)
    session = manager.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetail(
        **session.model_dump(),
        suggestions=manager.suggestions.for_session(session_id),
        transcript=manager.transcripts.for_session(session_id),
    )


@router.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, request: Request) -> None:
    manager = _manager(request)
    current = manager.current
    if current and current.id == session_id:
        raise HTTPException(status_code=409, detail="Stop the session before deleting it.")
    if not manager.sessions.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found")


class CaptureModeBody(BaseModel):
    mode: Literal["both", "mic", "system"]


@router.get("/api/audio/mode")
def get_capture_mode(request: Request) -> dict:
    return {"mode": _manager(request).capture_mode}


@router.put("/api/audio/mode")
async def set_capture_mode(body: CaptureModeBody, request: Request) -> dict:
    try:
        return {"mode": await _manager(request).set_capture_mode(body.mode)}
    except SessionError as exc:
        raise _conflict(exc) from exc


class ReadAloudBody(BaseModel):
    read_aloud: bool


class SpeakBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


@router.get("/api/tts")
def get_tts(request: Request) -> dict:
    return _manager(request).tts_state()


@router.put("/api/tts")
async def set_tts(body: ReadAloudBody, request: Request) -> dict:
    return await _manager(request).set_read_aloud(body.read_aloud)


@router.post("/api/tts/stop", status_code=204)
def stop_tts(request: Request) -> None:
    _manager(request).stop_speaking()


@router.post("/api/tts/speak", status_code=204)
def speak_tts(body: SpeakBody, request: Request) -> None:
    """Read a given answer aloud (the replay button on a suggestion)."""
    _manager(request).speak(body.text)


class ProfileBody(BaseModel):
    text: str = Field(max_length=40_000)


@router.get("/api/profile")
def get_profile(request: Request) -> dict:
    return {"text": _manager(request).profile}


@router.put("/api/profile")
def set_profile(body: ProfileBody, request: Request) -> dict:
    """Personal context (CV, experience, target job). Saved locally, included in every answer."""
    return {"text": _manager(request).set_profile(body.text)}


@router.get("/api/style")
def get_style(request: Request) -> dict:
    return _manager(request).get_answer_style()


@router.put("/api/style")
def set_style(body: ProfileBody, request: Request) -> dict:
    """How answers should sound. Empty text restores the default style."""
    return _manager(request).set_answer_style(body.text)


@router.post("/api/screenshot")
async def screenshot(request: Request) -> dict:
    """Capture the screen, read its text (Windows OCR), add it to the context and answer it."""
    try:
        return await _manager(request).capture_screen()
    except SessionError as exc:
        raise _conflict(exc) from exc


@router.post("/api/assistant/ask", response_model=Suggestion, status_code=202)
async def ask(body: AskRequest, request: Request) -> Suggestion:
    """Returns immediately; the answer streams over the WebSocket as assistant.* events."""
    return _manager(request).ask(body.question)


@router.post("/api/assistant/answer-now", response_model=Suggestion, status_code=202)
async def answer_now(request: Request) -> Suggestion:
    """Answer what was just said, without waiting for a question to be detected."""
    try:
        return await _manager(request).answer_now()
    except SessionError as exc:
        raise _conflict(exc) from exc


@router.websocket("/ws")
async def events_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    manager: SessionManager = websocket.app.state.manager
    queue = manager.events.subscribe()
    try:
        current = manager.current
        await websocket.send_json(
            {"type": "session.state", "payload": {"session": current.model_dump() if current else None}}
        )
        await websocket.send_json({"type": "audio.mode", "payload": {"mode": manager.capture_mode}})
        await websocket.send_json({"type": "tts.state", "payload": manager.tts_state()})
        usage = getattr(manager.provider, "last_rate_limit", None)
        if usage:
            await websocket.send_json({"type": "assistant.usage", "payload": usage})
        if manager.audio_status is not None:
            await websocket.send_json({"type": "audio.status", "payload": manager.audio_status})
        receiver = asyncio.create_task(_drain_client(websocket))
        while not receiver.done():
            getter = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                await websocket.send_json(getter.result())
            else:
                getter.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        manager.events.unsubscribe(queue)


async def _drain_client(websocket: WebSocket) -> None:
    """Consume client pings; returns when the client disconnects."""
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
