"""Application settings, read from environment variables (prefix ``COPILOT_``)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "AIInterviewCopilot"


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    phone_port: int = 8766            # phone view (local network), only while turned on
    data_dir: Path = field(default_factory=_default_data_dir)
    # "auto" (default): API if ANTHROPIC_API_KEY is set, else the Claude subscription via Claude Code.
    # "claude" = API, "claude-code" = subscription via the Claude Code CLI, "echo" = offline stub.
    ai_provider: str = "auto"
    ai_model: str = "claude-opus-5-5"
    # Interview suggestions must be fast; "low" effort keeps latency down. Raise for harder questions.
    ai_effort: str = "low"
    # Audio + on-device speech-to-text (faster-whisper on CPU).
    audio_enabled: bool = True
    stt_model: str = "base"           # tiny | base | small | medium: "base" runs ~6x realtime on a 4-core laptop CPU
    stt_language: str = ""            # "" = auto-detect per utterance; "en" / "es" is faster and more reliable
    stt_threads: int = 4
    auto_suggest: bool = True         # answer detected interviewer questions automatically
    ocr_language: str = ""           # "" = auto (Spanish engine if installed: reads English too)
    tts_enabled: bool = True          # read answers aloud with built-in Windows voices (toggle in the UI)
    allowed_origins: tuple[str, ...] = (
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "copilot.sqlite3"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"


def load_settings() -> Settings:
    env = os.environ
    d = Settings()
    return Settings(
        host=env.get("COPILOT_HOST", d.host),
        port=int(env.get("COPILOT_PORT", d.port)),
        phone_port=int(env.get("COPILOT_PHONE_PORT", d.phone_port)),
        data_dir=Path(env["COPILOT_DATA_DIR"]) if "COPILOT_DATA_DIR" in env else d.data_dir,
        ai_provider=env.get("COPILOT_AI_PROVIDER", d.ai_provider),
        ai_model=env.get("COPILOT_AI_MODEL", d.ai_model),
        ai_effort=env.get("COPILOT_AI_EFFORT", d.ai_effort),
        audio_enabled=_bool(env["COPILOT_AUDIO_ENABLED"]) if "COPILOT_AUDIO_ENABLED" in env else d.audio_enabled,
        stt_model=env.get("COPILOT_STT_MODEL", d.stt_model),
        stt_language=env.get("COPILOT_STT_LANGUAGE", d.stt_language),
        stt_threads=int(env.get("COPILOT_STT_THREADS", d.stt_threads)),
        auto_suggest=_bool(env["COPILOT_AUTO_SUGGEST"]) if "COPILOT_AUTO_SUGGEST" in env else d.auto_suggest,
        ocr_language=env.get("COPILOT_OCR_LANGUAGE", d.ocr_language),
        tts_enabled=_bool(env["COPILOT_TTS_ENABLED"]) if "COPILOT_TTS_ENABLED" in env else d.tts_enabled,
    )
