"""FastAPI entry point: ``python -m uvicorn app.main:app --port 8765`` from ``backend/``."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import Settings, load_settings
from app.core.events import EventBus
from app.models.db import Database
from app.repositories.sessions import (
    PreferenceRepository,
    SessionRepository,
    SuggestionRepository,
    TranscriptRepository,
)
from app.services.ai import build_provider
from app.services.session_manager import AudioFactory, SessionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def build_audio_factory(settings: Settings) -> AudioFactory | None:
    if not settings.audio_enabled:
        return None
    from app.services.audio.pipeline import AudioPipeline
    from app.services.audio.sources import build_sources
    from app.services.transcription.whisper import WhisperTranscriber

    # One model instance shared by every session; loaded on the first session start.
    transcriber = WhisperTranscriber(
        model_size=settings.stt_model,
        language=settings.stt_language,
        threads=settings.stt_threads,
        download_root=settings.models_dir,
    )

    def factory(mode, on_segment, on_status) -> AudioPipeline:
        return AudioPipeline(build_sources(mode), transcriber, on_segment, on_status)

    return factory


def build_speaker_factory(settings: Settings):
    if not settings.tts_enabled or sys.platform != "win32":
        return None
    from app.services.tts.speaker import SapiSpeaker

    return SapiSpeaker


def build_screen_reader(settings: Settings):
    if sys.platform != "win32":
        return None
    from app.services.vision.screen import read_screen

    return lambda: read_screen(settings.ocr_language)


def create_app(
    settings: Settings | None = None,
    audio_factory: AudioFactory | None = None,
    speaker_factory=None,
    screen_reader=None,
) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.db_path)
        sessions = SessionRepository(db)
        sessions.mark_orphans_stopped()
        app.state.settings = settings
        app.state.manager = SessionManager(
            sessions=sessions,
            suggestions=SuggestionRepository(db),
            transcripts=TranscriptRepository(db),
            provider=build_provider(settings),
            events=EventBus(),
            audio_factory=audio_factory or build_audio_factory(settings),
            auto_suggest=settings.auto_suggest,
            preferences=PreferenceRepository(db),
            speaker_factory=speaker_factory or build_speaker_factory(settings),
            screen_reader=screen_reader or build_screen_reader(settings),
        )
        yield
        await app.state.manager.shutdown()
        db.close()

    app = FastAPI(title="AI Interview Copilot", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    s = load_settings()
    uvicorn.run(app, host=s.host, port=s.port)
