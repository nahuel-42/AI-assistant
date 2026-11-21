"""On-device speech-to-text with faster-whisper (CPU, int8). Audio never leaves the computer."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Protocol

import numpy as np

# Phrases Whisper tends to invent on silence or noise.
_HALLUCINATIONS = {
    "you", "thank you.", "thank you", "thanks for watching!", "thank you for watching.",
    "thanks for watching.", "bye.", "gracias.", "¡gracias!", "gracias por ver el video.",
    "subtítulos realizados por la comunidad de amara.org", "¡suscríbete!",
}


class Transcriber(Protocol):
    def load(self) -> None: ...

    def transcribe(self, audio: np.ndarray) -> str: ...


class WhisperTranscriber:
    def __init__(self, model_size: str, language: str, threads: int, download_root: Path) -> None:
        self.model_size = model_size
        self.language = language or None
        self.threads = threads
        self.download_root = download_root
        self._model = None
        self._lock = threading.Lock()

    def load(self) -> None:
        """Downloads the model on first use (to the app data folder), then keeps it in memory."""
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self.download_root.mkdir(parents=True, exist_ok=True)
                kwargs = dict(
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=self.threads,
                    download_root=str(self.download_root),
                )
                try:
                    # Use the copy on disk without contacting the internet (fast, works offline).
                    self._model = WhisperModel(self.model_size, local_files_only=True, **kwargs)
                except Exception:  # noqa: BLE001 - not downloaded yet
                    self._model = WhisperModel(self.model_size, **kwargs)

    def transcribe(self, audio: np.ndarray) -> str:
        self.load()
        with self._lock:  # one decode at a time keeps CPU use predictable during the call
            segments, _info = self._model.transcribe(
                audio,
                language=self.language,
                beam_size=1,                       # greedy: much faster on CPU, small accuracy cost
                vad_filter=True,                   # drop non-speech inside the utterance
                condition_on_previous_text=False,  # avoids repetition loops
            )
            parts = [s.text.strip() for s in segments if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0]
        text = " ".join(p for p in parts if p).strip()
        return "" if text.lower() in _HALLUCINATIONS else text
