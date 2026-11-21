"""Owns the single live interview session: its audio pipeline, context and suggestions."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from app.core.events import EventBus
from app.repositories.sessions import (
    PreferenceRepository,
    SessionRepository,
    SuggestionRepository,
    TranscriptRepository,
)
from app.schemas.session import Session, Suggestion
from app.services.ai import AIProvider, AIProviderError
from app.services.audio.pipeline import AudioPipeline, SegmentCallback, StatusCallback
from app.services.audio.sources import CAPTURE_MODES
from app.services.context.manager import (
    DEFAULT_ANSWER_STYLE,
    SCREEN_HELP_REQUEST,
    SPEAKER_LABELS,
    InterviewContext,
)
from app.services.context.questions import looks_like_question
from app.services.tts.speaker import Speaker, speakable_part

log = logging.getLogger(__name__)

AudioFactory = Callable[[str, SegmentCallback, StatusCallback], AudioPipeline]  # (mode, ...)
SpeakerFactory = Callable[[Callable[[bool], None]], Speaker]  # (on_state) -> speaker
ScreenReader = Callable[[], str]  # blocking: capture the screen, return its text

# The copilot helps with every question, whoever asks it: the interviewer (computer sound), the
# user ("You", their mic) or anyone in the room ("unknown", mic-only capture).
QUESTION_SPEAKERS = {"interviewer", "user", "unknown"}

# The same question can arrive twice (mic picks up the call's sound): answer it only once.
DUPLICATE_WINDOW_S = 12.0
DUPLICATE_SIMILARITY = 0.6
MAX_ANSWER_NOW_LINES = 8  # how much of what was said the answer key sends at most


class SessionError(RuntimeError):
    pass


class SessionManager:
    def __init__(
        self,
        sessions: SessionRepository,
        suggestions: SuggestionRepository,
        transcripts: TranscriptRepository,
        provider: AIProvider,
        events: EventBus,
        audio_factory: AudioFactory | None = None,
        auto_suggest: bool = True,
        preferences: PreferenceRepository | None = None,
        speaker_factory: SpeakerFactory | None = None,
        screen_reader: ScreenReader | None = None,
    ) -> None:
        self.sessions = sessions
        self.suggestions = suggestions
        self.transcripts = transcripts
        self.provider = provider
        self.events = events
        self.audio_factory = audio_factory
        self.auto_suggest = auto_suggest
        self._current_id: str | None = None
        self._context = InterviewContext()
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._pipeline: AudioPipeline | None = None
        self.audio_status: dict[str, Any] | None = None
        self.preferences = preferences
        self.screen_reader = screen_reader
        # Personal context (CV, experience, job target): always sent, kept between sessions.
        self.profile = preferences.get("profile", "") if preferences else ""
        self._context.personal = self.profile
        # How answers should sound (tone, structure). Editable; empty means the default style.
        self.answer_style = preferences.get("answer_style", "") if preferences else ""
        self._context.style = self.answer_style or DEFAULT_ANSWER_STYLE
        mode = preferences.get("capture_mode", "both") if preferences else "both"
        self.capture_mode = mode if mode in CAPTURE_MODES else "both"
        # Read answers aloud (built-in Windows voices). On by default; the choice is remembered.
        self.read_aloud = (preferences.get("read_aloud", "true") if preferences else "true") == "true"
        self.speaking = False
        self.speaker: Speaker | None = None
        if speaker_factory:
            loop = asyncio.get_running_loop()

            def on_speech_state(speaking: bool) -> None:  # called from the TTS thread
                self.speaking = speaking
                self._submit(loop, self._publish_tts_state())

            self.speaker = speaker_factory(on_speech_state)
        # At most one automatic suggestion runs at a time; the newest waiting question wins.
        self._auto_running = False
        self._auto_pending: tuple[str, str] | None = None  # (question, asked_by)
        self._recent_questions: list[tuple[float, str]] = []
        # What was said since the last answer: what the answer key ("answer now") responds to.
        self._unanswered: list[str] = []
        self._answering_now = False  # while True, question detection doesn't also fire

    # ---- lifecycle -------------------------------------------------------

    @property
    def current(self) -> Session | None:
        return self.sessions.get(self._current_id) if self._current_id else None

    async def start(self, title: str | None = None) -> Session:
        async with self._lock:
            if self._current_id:
                raise SessionError("A session is already running. Stop it first.")
            session = self.sessions.create(
                uuid.uuid4().hex, title or f"Interview {datetime.now():%Y-%m-%d %H:%M}"
            )
            self._current_id = session.id
            self._context = InterviewContext(
                personal=self.profile, style=self.answer_style or DEFAULT_ANSWER_STYLE
            )
            self._auto_pending = None
            self._unanswered = []
            await self._start_capture(session.id)
        await self._broadcast_state()
        return session

    async def pause(self) -> Session:
        return await self._transition("paused", allowed_from={"active"})

    async def resume(self) -> Session:
        return await self._transition("active", allowed_from={"paused"})

    async def stop(self) -> Session:
        async with self._lock:
            if not self._current_id:
                raise SessionError("No session is running.")
            session_id = self._current_id
            self._current_id = None
            self._auto_pending = None
            await self._stop_capture()
            self.sessions.set_status(session_id, "stopped")
        await self._broadcast_state()
        session = self.sessions.get(session_id)
        assert session is not None
        return session

    async def _transition(self, status: str, allowed_from: set[str]) -> Session:
        async with self._lock:
            session = self.current
            if not session:
                raise SessionError("No session is running.")
            if session.status not in allowed_from:
                raise SessionError(f"Cannot change a {session.status} session to {status}.")
            if status == "paused":
                await self._stop_capture()  # pausing really stops the microphone and loopback
            else:
                await self._start_capture(session.id)
            self.sessions.set_status(session.id, status)
        await self._broadcast_state()
        updated = self.current
        assert updated is not None
        return updated

    async def _broadcast_state(self) -> None:
        session = self.current
        await self.events.publish("session.state", {"session": session.model_dump() if session else None})

    # ---- audio -----------------------------------------------------------

    async def _start_capture(self, session_id: str) -> None:
        if not self.audio_factory or self._pipeline:
            return
        loop = asyncio.get_running_loop()

        def on_segment(speaker: str, text: str) -> None:  # called from the STT worker thread
            self._submit(loop, self._on_segment(session_id, speaker, text))

        def on_status(status: dict[str, Any]) -> None:  # called from capture threads
            self._submit(loop, self._on_audio_status(status))

        self._pipeline = self.audio_factory(self.capture_mode, on_segment, on_status)
        # While an answer is read aloud, ignore every input: any of them could hear the voice and
        # trigger a suggestion, and the app would answer itself.
        self._pipeline.mute = lambda who: (
            who in QUESTION_SPEAKERS and self.speaker is not None and self.speaker.is_speaking()
        )
        await asyncio.to_thread(self._pipeline.start)

    async def set_capture_mode(self, mode: str) -> str:
        """Switch inputs; applies immediately if a session is recording."""
        if mode not in CAPTURE_MODES:
            raise SessionError(f"Unknown capture mode {mode!r}")
        async with self._lock:
            self.capture_mode = mode
            if self.preferences:
                self.preferences.set("capture_mode", mode)
            session = self.current
            if session and session.status == "active":
                await self._stop_capture()
                await self._start_capture(session.id)
        await self.events.publish("audio.mode", {"mode": mode})
        return mode

    async def _stop_capture(self) -> None:
        pipeline, self._pipeline = self._pipeline, None
        if pipeline:
            await asyncio.to_thread(pipeline.stop)

    @staticmethod
    def _submit(loop: asyncio.AbstractEventLoop, coro) -> None:
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:  # loop closed during shutdown
            coro.close()

    async def _on_audio_status(self, status: dict[str, Any]) -> None:
        self.audio_status = status
        await self.events.publish("audio.status", status)

    async def _on_segment(self, session_id: str, speaker: str, text: str) -> None:
        is_question = speaker in QUESTION_SPEAKERS and looks_like_question(text)
        segment = self.transcripts.add(session_id, speaker, text, is_question)
        await self.events.publish("transcript.segment", segment.model_dump())
        if session_id != self._current_id:
            return  # late result from a session that has already ended
        self._context.add_transcript(speaker, text)
        if speaker in QUESTION_SPEAKERS:
            self._unanswered.append(f"{SPEAKER_LABELS.get(speaker, speaker)}: {text}")
            del self._unanswered[:-MAX_ANSWER_NOW_LINES]
        session = self.current
        if (
            is_question
            and not self._answering_now
            and self.auto_suggest
            and session
            and session.status == "active"
            and not self._is_duplicate_question(text)
        ):
            self._auto_ask(text, speaker)

    def _is_duplicate_question(self, text: str) -> bool:
        now = time.monotonic()
        self._recent_questions = [(t, q) for t, q in self._recent_questions if now - t < DUPLICATE_WINDOW_S]
        normalized = text.lower().strip()
        duplicate = any(
            SequenceMatcher(None, normalized, q).ratio() >= DUPLICATE_SIMILARITY for _, q in self._recent_questions
        )
        self._recent_questions.append((now, normalized))
        return duplicate

    def _auto_ask(self, question: str, asked_by: str) -> None:
        if self._auto_running:
            self._auto_pending = (question, asked_by)
            return
        self._auto_running = True
        self._unanswered = []
        self.ask(question, auto=True, asked_by=asked_by)

    async def answer_now(self) -> Suggestion:
        """Answer what was just said, on the user's request (answer key or button).

        Doesn't wait for question detection: it answers whatever was said since the last answer,
        including the sentence still being spoken when the key was pressed.
        """
        session = self.current
        self._answering_now = True
        try:
            if self._pipeline and session and session.status == "active":
                await asyncio.to_thread(self._pipeline.flush)
                await asyncio.sleep(0.05)  # let the segments just transcribed reach the context
        finally:
            self._answering_now = False
        heard = self._unanswered or self._context.recent_transcript[-3:]
        if not heard:
            raise SessionError("Nothing has been said yet. Start a session, or type your question.")
        self._unanswered = []
        self._auto_pending = None  # this answer covers any question still waiting
        return self.ask("\n".join(heard), auto=True, asked_by="manual")

    # ---- assistant -------------------------------------------------------

    def ask(self, question: str, auto: bool = False, asked_by: str = "typed") -> Suggestion:
        """Create a suggestion and stream it over the event bus in the background.

        ``asked_by``: "interviewer" | "user" | "unknown" (heard in the room) | "typed".
        """
        suggestion = self.suggestions.create(uuid.uuid4().hex, self._current_id, question, auto=auto)
        task = asyncio.create_task(self._stream_suggestion(suggestion, self._context, asked_by))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return suggestion

    async def _stream_suggestion(self, suggestion: Suggestion, context: InterviewContext, asked_by: str) -> None:
        try:
            await self._run_suggestion(suggestion, context, asked_by)
        finally:
            if suggestion.auto and asked_by in QUESTION_SPEAKERS:  # the detected-question chain
                self._auto_running = False
                pending, self._auto_pending = self._auto_pending, None
                if pending and self._current_id:
                    self._auto_ask(*pending)

    async def _run_suggestion(self, suggestion: Suggestion, context: InterviewContext, asked_by: str) -> None:
        await self.events.publish("assistant.started", suggestion.model_dump())
        parts: list[str] = []
        try:
            async for delta in self.provider.stream_answer(
                context.build_system(), context.build_messages(suggestion.prompt, asked_by)
            ):
                parts.append(delta)
                await self.events.publish("assistant.delta", {"id": suggestion.id, "delta": delta})
        except AIProviderError as exc:
            self.suggestions.finish(suggestion.id, "".join(parts), "error")
            await self.events.publish("assistant.error", {"id": suggestion.id, "message": str(exc)})
            await self._publish_usage()
            return
        except Exception:  # noqa: BLE001 - never let a background task die silently
            log.exception("Suggestion %s failed", suggestion.id)
            self.suggestions.finish(suggestion.id, "".join(parts), "error")
            await self.events.publish("assistant.error", {"id": suggestion.id, "message": "Unexpected error."})
            return
        answer = "".join(parts)
        self.suggestions.finish(suggestion.id, answer, "done")
        context.add_exchange(suggestion.prompt, answer)
        await self.events.publish("assistant.done", {"id": suggestion.id, "response": answer})
        if self.read_aloud and self.speaker:
            self.speaker.speak(speakable_part(answer))
        await self._publish_usage()

    # ---- profile -----------------------------------------------------------

    def set_profile(self, text: str) -> str:
        self.profile = text.strip()
        if self.preferences:
            self.preferences.set("profile", self.profile)
        self._context.personal = self.profile  # applies to the running session immediately
        return self.profile

    def get_answer_style(self) -> dict[str, Any]:
        return {"text": self.answer_style or DEFAULT_ANSWER_STYLE, "is_default": not self.answer_style}

    def set_answer_style(self, text: str) -> dict[str, Any]:
        """Empty text, or text equal to the default, restores the default style."""
        text = text.strip()
        self.answer_style = "" if text == DEFAULT_ANSWER_STYLE else text
        if self.preferences:
            self.preferences.set("answer_style", self.answer_style)
        self._context.style = self.answer_style or DEFAULT_ANSWER_STYLE
        return self.get_answer_style()

    # ---- screenshots -------------------------------------------------------

    async def capture_screen(self) -> dict[str, Any]:
        """Read the screen's text, add it to the context, and ask for help with it.

        Works with or without a running session; the text is saved to the session if there is one.
        """
        if not self.screen_reader:
            raise SessionError("Screen capture is not available.")
        try:
            text = await asyncio.to_thread(self.screen_reader)
        except Exception as exc:  # noqa: BLE001 - report capture/OCR failures to the user
            log.exception("Screen capture failed")
            raise SessionError(f"Screen capture failed: {exc}") from exc
        if not text.strip():
            return {"chars": 0, "text": "", "suggestion_id": None}
        if self._current_id:
            segment = self.transcripts.add(self._current_id, "screen", text, False)
            await self.events.publish("transcript.segment", segment.model_dump())
        self._context.add_screen(text)
        suggestion = self.ask(SCREEN_HELP_REQUEST, auto=True, asked_by="screen")
        return {"chars": len(text), "text": text, "suggestion_id": suggestion.id}

    # ---- read aloud --------------------------------------------------------

    def tts_state(self) -> dict[str, Any]:
        return {"available": self.speaker is not None, "read_aloud": self.read_aloud, "speaking": self.speaking}

    async def _publish_tts_state(self) -> None:
        await self.events.publish("tts.state", self.tts_state())

    async def set_read_aloud(self, enabled: bool) -> dict[str, Any]:
        self.read_aloud = enabled
        if self.preferences:
            self.preferences.set("read_aloud", "true" if enabled else "false")
        if not enabled and self.speaker:
            self.speaker.stop()
        await self._publish_tts_state()
        return self.tts_state()

    def stop_speaking(self) -> None:
        if self.speaker:
            self.speaker.stop()

    def speak(self, text: str) -> None:
        if self.speaker:
            self.speaker.speak(speakable_part(text))

    async def _publish_usage(self) -> None:
        """Subscription providers report how much of the plan's usage window is used."""
        info = getattr(self.provider, "last_rate_limit", None)
        if info:
            await self.events.publish("assistant.usage", info)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self.speaker:
            self.speaker.close()
        await self._stop_capture()
        if self._current_id:
            self.sessions.set_status(self._current_id, "stopped")
            self._current_id = None
