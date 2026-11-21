"""Provider abstraction so Claude can be swapped for other models later (PRD §2 Modularity)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class AIProviderError(RuntimeError):
    """Raised for failures the UI should show to the user (refusals, auth, rate limits)."""


class AIProvider(ABC):
    name: str

    @abstractmethod
    def stream_answer(self, system: str, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        """Yield response text incrementally."""


class EchoProvider(AIProvider):
    """Offline stand-in: lets the app and tests run without credentials or network."""

    name = "echo"

    async def stream_answer(self, system: str, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        last = messages[-1]["content"] if messages else ""
        text = last if isinstance(last, str) else "(non-text input)"
        for word in f"[echo provider] You asked: {text}".split(" "):
            yield word + " "
