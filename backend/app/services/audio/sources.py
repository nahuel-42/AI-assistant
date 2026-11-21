"""Audio inputs. ``SoundcardSource`` uses WASAPI: the default microphone, or loopback of the
default speakers (what the meeting app is playing, i.e. the interviewer)."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
import warnings
from collections.abc import Callable
from typing import Protocol

import numpy as np

from app.services.audio.segmenter import SAMPLE_RATE

# soundcard initialises COM when imported and treats "already initialised" (S_FALSE) as an error,
# so it must be imported once here, on the startup thread, before any capture thread calls
# CoInitializeEx. Importing it lazily inside a capture thread fails with "Error 0x100000001".
import soundcard as sc  # noqa: E402

ChunkCallback = Callable[[np.ndarray], None]


DeviceCallback = Callable[[str], None]

# Which inputs to capture: both sides of a call, only one of them.
CAPTURE_MODES = ("both", "mic", "system")


class AudioSource(Protocol):
    speaker: str  # "user" | "interviewer" | "unknown"
    kind: str     # "mic" | "system" (status key)

    def run(self, on_chunk: ChunkCallback, stop: threading.Event, on_device: DeviceCallback) -> None:
        """Block, delivering mono float32 16 kHz chunks, until ``stop`` is set.
        ``on_device`` is called with the device name whenever capture (re)opens a device."""


class SoundcardSource:
    """Captures the *current* Windows default device and follows it when the default changes
    (e.g. a headset is plugged in mid-session)."""

    DEVICE_CHECK_S = 2.0

    def __init__(self, loopback: bool, speaker: str | None = None, block_frames: int = SAMPLE_RATE // 10) -> None:
        self.loopback = loopback
        self.speaker = speaker or ("interviewer" if loopback else "user")
        self.kind = "system" if loopback else "mic"
        self.block_frames = block_frames

    def _device(self):
        if self.loopback:
            return sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
        return sc.default_microphone()

    def _default_name(self) -> str:
        return (sc.default_speaker() if self.loopback else sc.default_microphone()).name

    def run(self, on_chunk: ChunkCallback, stop: threading.Event, on_device: DeviceCallback) -> None:
        _co_initialize()  # WASAPI is COM; every capture thread must initialise it
        # "data discontinuity" just means a few ms were dropped under load; harmless for speech.
        warnings.filterwarnings("ignore", message="data discontinuity")
        while not stop.is_set():
            device = self._device()
            opened_for = self._default_name()
            on_device(device.name)
            next_check = time.monotonic() + self.DEVICE_CHECK_S
            with device.recorder(samplerate=SAMPLE_RATE, blocksize=self.block_frames) as rec:
                while not stop.is_set():
                    data = rec.record(numframes=self.block_frames)
                    mono = data.mean(axis=1) if data.ndim == 2 else data
                    on_chunk(mono.astype(np.float32, copy=False))
                    if time.monotonic() >= next_check:
                        next_check = time.monotonic() + self.DEVICE_CHECK_S
                        if self._default_name() != opened_for:
                            break  # default device changed: reopen on the new one


def build_sources(mode: str) -> list[SoundcardSource]:
    if mode == "mic":
        # Mic alone hears everyone in the room (in-person interview, or practising aloud).
        return [SoundcardSource(loopback=False, speaker="unknown")]
    if mode == "system":
        return [SoundcardSource(loopback=True)]
    return [SoundcardSource(loopback=False), SoundcardSource(loopback=True)]


def _co_initialize() -> None:
    if sys.platform == "win32":
        ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED; repeat calls are harmless
