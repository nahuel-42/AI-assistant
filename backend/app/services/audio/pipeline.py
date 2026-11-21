"""Capture threads -> utterance segmenters -> one transcription worker -> callback.

Runs entirely in background threads; the session manager bridges results back to asyncio.
Raw audio is kept in memory only until it is transcribed and is never written to disk.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from app.services.audio.segmenter import UtteranceSegmenter
from app.services.audio.sources import AudioSource
from app.services.transcription.whisper import Transcriber

log = logging.getLogger(__name__)

SegmentCallback = Callable[[str, str], None]          # (speaker, text)
StatusCallback = Callable[[dict[str, Any]], None]

_STOP = object()


class AudioPipeline:
    def __init__(
        self,
        sources: list[AudioSource],
        transcriber: Transcriber,
        on_segment: SegmentCallback,
        on_status: StatusCallback,
    ) -> None:
        self.sources = sources
        self.transcriber = transcriber
        self.on_segment = on_segment
        self.on_status = on_status
        # Set by the session manager: returns True while a speaker's audio must be ignored
        # (e.g. the app is reading an answer aloud and would otherwise transcribe itself).
        self.mute: Callable[[str], bool] | None = None
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._worker: threading.Thread | None = None
        self._status_lock = threading.Lock()
        # flush(): capture threads that still have to cut their utterance in progress
        self._flush_cv = threading.Condition()
        self._flush_waiting: set[str] = set()
        self.status: dict[str, Any] = {s.kind: "starting" for s in sources}
        self.status.update(stt="loading", devices={}, message=None)

    # ---- control ---------------------------------------------------------

    def start(self) -> None:
        self._emit_status()
        self._worker = threading.Thread(target=self._work, name="stt-worker", daemon=True)
        self._worker.start()
        for source in self.sources:
            t = threading.Thread(target=self._capture, args=(source,), name=f"capture-{source.kind}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=3)
        # The worker finishes already-queued utterances in the background, then exits. Not joined:
        # stopping must feel instant, and late results are still saved to the right session.
        self._queue.put(_STOP)
        self._set_status({s.kind: "off" for s in self.sources} | {"stt": "off"})

    def flush(self, timeout: float = 4.0) -> bool:
        """Cut every utterance in progress and wait until all audio heard so far is transcribed.

        Used when the user asks for an answer right now: the sentence still being spoken (or in
        its trailing 0.8 s of silence) must be part of it. Returns False on timeout.
        """
        deadline = time.monotonic() + timeout
        with self._flush_cv:
            self._flush_waiting = {s.kind for s in self.sources if self.status.get(s.kind) == "on"}
            self._flush_cv.wait_for(lambda: not self._flush_waiting, timeout=min(1.0, timeout))
            self._flush_waiting = set()
        done = threading.Event()  # queued after the cut utterances: set once they are transcribed
        self._queue.put(done)
        return done.wait(max(0.1, deadline - time.monotonic()))

    # ---- threads ---------------------------------------------------------

    def _capture(self, source: AudioSource) -> None:
        segmenter = UtteranceSegmenter()

        def on_chunk(chunk: np.ndarray) -> None:
            if self.mute is not None and self.mute(source.speaker):
                # Feed silence instead of dropping: an utterance in progress then ends cleanly.
                chunk = np.zeros_like(chunk)
            for utterance in segmenter.feed(chunk):
                self._queue.put((source.speaker, utterance))
            if source.kind in self._flush_waiting:
                with self._flush_cv:
                    if source.kind in self._flush_waiting:
                        tail = segmenter.flush()
                        if tail is not None:
                            self._queue.put((source.speaker, tail))
                        self._flush_waiting.discard(source.kind)
                        self._flush_cv.notify_all()

        def on_device(name: str) -> None:
            with self._status_lock:
                self.status["devices"] = {**self.status["devices"], source.kind: name}
            self._set_status({source.kind: "on"})

        try:
            source.run(on_chunk, self._stop, on_device)
        except Exception as exc:  # noqa: BLE001 - surface any device failure to the UI
            log.exception("Audio capture failed for %s", source.kind)
            self._set_status({source.kind: "error", "message": f"{source.kind} capture failed: {exc}"})
        finally:
            tail = segmenter.flush()
            if tail is not None:
                self._queue.put((source.speaker, tail))

    def _work(self) -> None:
        try:
            self.transcriber.load()
            self._set_status({"stt": "ready"})
        except Exception as exc:  # noqa: BLE001
            log.exception("Speech model failed to load")
            self._set_status({"stt": "error", "message": f"Speech model failed to load: {exc}"})
            return
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            if isinstance(item, threading.Event):  # a flush() marker: everything before it is done
                item.set()
                continue
            speaker, audio = item
            try:
                text = self.transcriber.transcribe(audio)
            except Exception:  # noqa: BLE001 - one bad utterance must not kill the worker
                log.exception("Transcription failed")
                continue
            if text:
                self.on_segment(speaker, text)

    # ---- status ----------------------------------------------------------

    def _set_status(self, changes: dict[str, Any]) -> None:
        with self._status_lock:
            self.status.update(changes)
        self._emit_status()

    def _emit_status(self) -> None:
        with self._status_lock:
            snapshot = dict(self.status)
        self.on_status(snapshot)
