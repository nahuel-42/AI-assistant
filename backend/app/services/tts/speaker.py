"""Reads suggestions aloud with the built-in Windows voices (SAPI). Free and offline.

SAPI is COM, so one dedicated thread owns the voice object; other threads send it commands.
Speech goes to the Windows default output device, i.e. the user's headphones.
"""

from __future__ import annotations

import logging
import queue
import re
import sys
import threading
import time
from collections.abc import Callable
from typing import Protocol

log = logging.getLogger(__name__)

_SVSF_ASYNC = 1
_SVSF_PURGE = 2           # drop anything queued or currently being spoken
_PRIMARY_LANG = {"en": 0x09, "es": 0x0A}
# After speech ends, keep ignoring computer sound briefly: device buffers still hold the tail.
_ECHO_GUARD_S = 0.6


class Speaker(Protocol):
    def speak(self, text: str) -> None: ...
    def stop(self) -> None: ...
    def is_speaking(self) -> bool: ...
    def close(self) -> None: ...


# ---- text preparation -------------------------------------------------------

_SPANISH_HINTS = re.compile(r"[ñ¿¡áéíóú]|\b(el|la|los|las|que|de|en|un|una|es|con|para|por|como)\b", re.IGNORECASE)


def detect_language(text: str) -> str:
    """Good enough to pick between the installed English and Spanish voices."""
    words = max(len(text.split()), 1)
    return "es" if len(_SPANISH_HINTS.findall(text)) / words > 0.12 else "en"


_BULLET = re.compile(r"^([-*•]|\d+[.)])\s+")


def _clean(line: str) -> str:
    line = _BULLET.sub("", line.strip())
    line = re.sub(r"\*\*|__|`|^#+\s*|^>\s*", "", line)          # bold, code, headings, quotes
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)         # links -> their text
    line = re.sub(r"\s*\([^()]{1,30}\)(?=\s*[:,.])", "", line)  # short asides: "Context (1 sentence):"
    line = line.replace("*", "").replace('"', "").replace("“", "").replace("”", "")
    return re.sub(r"\s{2,}", " ", line).strip()


def _is_note(text: str) -> bool:
    """Meta remarks like "(No resume uploaded, so here's a template.)" are for reading, not saying."""
    return text.startswith("(") and text.endswith(")")


def speakable_part(answer: str, max_words: int = 150) -> str:
    """The short 'say this' part of an answer, as plain text for the voice.

    Reads the first paragraph(s) up to the supporting bullet points, skipping notes in
    parentheses. When the text introduces a list ("...in three steps:"), the list is read too.
    """
    spoken: list[str] = []
    allow_list = False

    def text() -> str:
        return " ".join(spoken)

    for paragraph in re.split(r"\n\s*\n", answer.strip()):
        for raw in paragraph.splitlines():
            if not raw.strip():
                continue
            is_bullet = bool(_BULLET.match(raw.strip()))
            line = _clean(raw)
            if not line or _is_note(line):
                continue
            if is_bullet and spoken and not allow_list:
                return _cap(text(), max_words)  # supporting bullets are for reading only
            spoken.append(line)
            if line.endswith(":"):
                allow_list = True
            if len(text().split()) >= max_words:
                return _cap(text(), max_words)
        if spoken and not text().endswith(":"):
            break
    return _cap(text() or _clean(answer), max_words)


def _cap(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]).rstrip(",;:") + "…"
    return text


# ---- SAPI implementation ------------------------------------------------------

class SapiSpeaker:
    def __init__(self, on_state: Callable[[bool], None]) -> None:
        self.on_state = on_state
        self._commands: queue.Queue[tuple[str, str]] = queue.Queue()
        self._speaking = False
        self._quiet_since = 0.0
        self._thread = threading.Thread(target=self._run, name="tts", daemon=True)
        self._thread.start()

    def speak(self, text: str) -> None:
        if text.strip():
            self._commands.put(("speak", text))

    def stop(self) -> None:
        self._commands.put(("stop", ""))

    def close(self) -> None:
        self._commands.put(("close", ""))

    def is_speaking(self) -> bool:
        return self._speaking or (time.monotonic() - self._quiet_since) < _ECHO_GUARD_S

    def _set_speaking(self, speaking: bool) -> None:
        if speaking == self._speaking:
            return
        self._speaking = speaking
        if not speaking:
            self._quiet_since = time.monotonic()
        self.on_state(speaking)

    def _run(self) -> None:
        if sys.platform != "win32":
            return
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        voices = voice.GetVoices()
        by_lang: dict[str, object] = {}
        for i in range(voices.Count):
            token = voices.Item(i)
            try:
                primary = int(token.GetAttribute("Language").split(";")[0], 16) & 0x3FF
            except (ValueError, comtypes.COMError):
                continue
            for lang, code in _PRIMARY_LANG.items():
                if primary == code:
                    by_lang.setdefault(lang, token)

        while True:
            try:
                command, text = self._commands.get(timeout=0.1)
            except queue.Empty:
                # WaitUntilDone(0) is True only once speech has really finished. RunningState is
                # not usable here: it reads 0 ("not speaking") for ~0.5 s after Speak() starts.
                if self._speaking and voice.WaitUntilDone(0):
                    self._set_speaking(False)
                continue
            try:
                if command == "close":
                    voice.Speak("", _SVSF_ASYNC | _SVSF_PURGE)
                    self._set_speaking(False)
                    return
                if command == "stop":
                    voice.Speak("", _SVSF_ASYNC | _SVSF_PURGE)
                    self._set_speaking(False)
                elif command == "speak":
                    token = by_lang.get(detect_language(text))
                    if token is not None:
                        voice.Voice = token
                    voice.Speak(text, _SVSF_ASYNC | _SVSF_PURGE)  # newest answer replaces the old one
                    self._set_speaking(True)
            except Exception:  # noqa: BLE001 - speech must never take the app down
                log.exception("Text-to-speech failed")
                self._set_speaking(False)
