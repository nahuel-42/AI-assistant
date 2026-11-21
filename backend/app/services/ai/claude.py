from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.services.ai.base import AIProvider, AIProviderError


class ClaudeProvider(AIProvider):
    name = "claude"

    def __init__(self, model: str, effort: str = "low") -> None:
        # Credentials resolve from ANTHROPIC_API_KEY or an `ant auth login` profile.
        self._client = anthropic.AsyncAnthropic()
        self._model = model
        self._effort = effort

    async def stream_answer(self, system: str, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        try:
            async with self._client.beta.messages.stream(
                model=self._model,
                # Suggestions are deliberately short; streaming keeps first-token latency low.
                max_tokens=4096,
                system=system,
                messages=messages,
                output_config={"effort": self._effort},
                # On a safety-classifier decline, the API re-runs the request on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                async for text in stream.text_stream:
                    yield text
                final = await stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise AIProviderError("Claude credentials missing or invalid. Set ANTHROPIC_API_KEY.") from exc
        except anthropic.RateLimitError as exc:
            raise AIProviderError("Claude rate limit reached; try again in a moment.") from exc
        except anthropic.APIStatusError as exc:
            raise AIProviderError(f"Claude API error {exc.status_code}.") from exc
        except anthropic.APIConnectionError as exc:
            raise AIProviderError("Could not reach the Claude API. Check your connection.") from exc

        if final.stop_reason == "refusal":
            raise AIProviderError("Claude declined to answer this request.")
