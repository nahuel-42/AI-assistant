"""Cheap heuristic for spotting interviewer questions (English and Spanish) in transcript text."""

from __future__ import annotations

import re

_STARTS = (
    # English
    "what", "why", "how", "when", "where", "who", "which", "can you", "could you", "would you",
    "will you", "do you", "did you", "have you", "are you", "is there", "tell me", "walk me through",
    "describe", "explain", "give me an example", "talk about", "talk me through", "share",
    # Spanish. Unaccented "como/cuando/que..." also open plain statements, so only the accented
    # interrogatives count; Whisper usually adds the accents and "¿" for real questions.
    "qué", "por qué", "cómo", "cuándo", "dónde", "quién", "cuál",
    "puedes", "podrías", "podrias", "has ", "tienes",
    "cuéntame", "cuentame", "háblame", "hablame", "describe", "explica", "explícame",
    "explicame", "dame un ejemplo",
)
_FILLERS = re.compile(
    r"^(so|okay|ok|alright|and|great|right|well|now|bueno|entonces|vale|y|perfecto|muy bien)[,\s]+",
    re.IGNORECASE,
)


def looks_like_question(text: str) -> bool:
    if len(text.split()) < 3:
        return False
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        s = sentence.strip()
        if not s:
            continue
        if s.endswith("?") or s.startswith("¿"):
            return True
        lowered = s.lower()
        while (m := _FILLERS.match(lowered)) is not None:
            lowered = lowered[m.end():]
        if lowered.startswith(_STARTS) and len(lowered.split()) >= 3:
            return True
    return False
