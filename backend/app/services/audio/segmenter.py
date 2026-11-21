"""Splits a continuous audio stream into utterances using an adaptive energy threshold.

Whisper works best on whole phrases, so each stream is cut at pauses: an utterance ends after
``silence_end_s`` of quiet, or is force-cut at ``max_utterance_s`` so long monologues still
produce text promptly.
"""

from __future__ import annotations

from collections import deque

import numpy as np

SAMPLE_RATE = 16_000


class UtteranceSegmenter:
    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        silence_end_s: float = 0.8,
        max_utterance_s: float = 15.0,
        min_speech_s: float = 0.4,
        pre_roll_s: float = 0.3,
        threshold_floor: float = 0.006,
    ) -> None:
        self.sample_rate = sample_rate
        self.silence_end_s = silence_end_s
        self.max_samples = int(max_utterance_s * sample_rate)
        self.min_speech_s = min_speech_s
        self.threshold_floor = threshold_floor
        self._pre_roll: deque[np.ndarray] = deque()
        self._pre_roll_samples = int(pre_roll_s * sample_rate)
        self._noise = threshold_floor
        self._reset()

    def _reset(self) -> None:
        self._in_speech = False
        self._buf: list[np.ndarray] = []
        self._buf_samples = 0
        self._speech_s = 0.0
        self._silence_s = 0.0

    def feed(self, chunk: np.ndarray) -> list[np.ndarray]:
        """Add mono float32 samples; returns any utterances completed by this chunk."""
        if chunk.size == 0:
            return []
        dur = chunk.size / self.sample_rate
        rms = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float32))))
        voiced = rms > max(self.threshold_floor, self._noise * 3.0)

        if not self._in_speech:
            if voiced:
                self._in_speech = True
                self._buf = list(self._pre_roll)
                self._buf_samples = sum(c.size for c in self._buf)
                self._pre_roll.clear()
                self._append(chunk)
                self._speech_s = dur
            else:
                self._noise = 0.95 * self._noise + 0.05 * rms  # track background level
                self._pre_roll.append(chunk)
                while sum(c.size for c in self._pre_roll) > self._pre_roll_samples:
                    self._pre_roll.popleft()
            return []

        self._append(chunk)
        if voiced:
            self._speech_s += dur
            self._silence_s = 0.0
        else:
            self._silence_s += dur
        if self._silence_s >= self.silence_end_s or self._buf_samples >= self.max_samples:
            done = self._finish()
            return [done] if done is not None else []
        return []

    def flush(self) -> np.ndarray | None:
        """Emit whatever is buffered (used when capture stops mid-sentence)."""
        return self._finish() if self._in_speech else None

    def _append(self, chunk: np.ndarray) -> None:
        self._buf.append(chunk)
        self._buf_samples += chunk.size

    def _finish(self) -> np.ndarray | None:
        audio = np.concatenate(self._buf) if self._buf else None
        enough = self._speech_s >= self.min_speech_s
        self._reset()
        return audio if enough else None
