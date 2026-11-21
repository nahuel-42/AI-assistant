"""Runs suggestions through the locally installed Claude Code CLI, using the user's own
claude.ai subscription (e.g. Pro) instead of API credits.

Each suggestion starts ``claude -p`` in headless mode with no tools, no session persistence and
customizations disabled. Any API key is removed from the child environment so Claude Code always
uses the subscription login and never bills an API account.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.services.ai.base import AIProvider, AIProviderError

log = logging.getLogger(__name__)

_STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDECODE")
_IDLE_TIMEOUT_S = 90


def find_claude_cli() -> str | None:
    explicit = os.environ.get("COPILOT_CLAUDE_CODE_PATH")
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    default = Path.home() / ".local" / "bin" / ("claude.exe" if sys.platform == "win32" else "claude")
    return str(default) if default.exists() else None


class ClaudeCodeProvider(AIProvider):
    name = "claude-code"

    def __init__(self, cli_path: str, model: str, effort: str, workdir: Path) -> None:
        self.cli_path = cli_path
        self.model = model
        self.effort = effort
        self.workdir = workdir  # empty folder, so no project files or CLAUDE.md are picked up
        self.last_rate_limit: dict[str, Any] | None = None

    async def stream_answer(self, system: str, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        self.workdir.mkdir(parents=True, exist_ok=True)
        fd, system_file = tempfile.mkstemp(prefix="copilot-system-", suffix=".txt", dir=self.workdir)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(system)

        args = [
            self.cli_path, "-p",
            "--output-format", "stream-json", "--verbose", "--include-partial-messages",
            "--tools", "",
            "--no-session-persistence",
            "--safe-mode", "--strict-mcp-config", "--disable-slash-commands",
            "--model", self.model,
            "--effort", self.effort,
            "--system-prompt-file", system_file,
        ]
        env = {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}
        loop = asyncio.get_running_loop()
        lines: asyncio.Queue[str | None] = asyncio.Queue()
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # no console popup

        try:
            proc = subprocess.Popen(
                args, cwd=self.workdir, env=env, creationflags=flags,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            os.unlink(system_file)
            raise AIProviderError(f"Could not start Claude Code: {exc}") from exc

        # Plain threads + a queue work with any asyncio event loop on Windows.
        def pump_stdout() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                loop.call_soon_threadsafe(lines.put_nowait, line)
            loop.call_soon_threadsafe(lines.put_nowait, None)

        stderr_tail: list[str] = []

        def pump_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_tail.append(line)
                del stderr_tail[:-20]

        threading.Thread(target=pump_stdout, daemon=True).start()
        threading.Thread(target=pump_stderr, daemon=True).start()
        assert proc.stdin is not None
        proc.stdin.write(_flatten(messages))
        proc.stdin.close()

        result: dict[str, Any] | None = None
        try:
            while True:
                try:
                    line = await asyncio.wait_for(lines.get(), timeout=_IDLE_TIMEOUT_S)
                except asyncio.TimeoutError as exc:
                    raise AIProviderError("Claude Code stopped responding.") from exc
                if line is None:
                    break
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("type")
                if kind == "stream_event":
                    ev = event.get("event", {})
                    delta = ev.get("delta", {})
                    if ev.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                        yield delta.get("text", "")
                elif kind == "rate_limit_event":
                    self.last_rate_limit = event.get("rate_limit_info")
                elif kind == "result":
                    result = event
        finally:
            if proc.poll() is None:
                proc.kill()  # cancelled or failed mid-stream
            await asyncio.to_thread(proc.wait)
            try:
                os.unlink(system_file)
            except OSError:
                pass

        if result is None:
            detail = "".join(stderr_tail).strip()[-300:] or f"exit code {proc.returncode}"
            raise AIProviderError(f"Claude Code failed: {detail}")
        if result.get("is_error"):
            raise AIProviderError(_friendly_error(str(result.get("result") or result.get("subtype"))))


def _flatten(messages: list[dict[str, Any]]) -> str:
    """Claude Code -p takes one prompt, so earlier Q&A turns are written out as context."""
    *history, last = messages
    parts: list[str] = []
    if history:
        parts.append("<earlier_in_this_interview>")
        for m in history:
            label = "Question" if m["role"] == "user" else "Your suggestion"
            parts.append(f"{label}: {m['content']}")
        parts.append("</earlier_in_this_interview>\n")
    parts.append(str(last["content"]))
    return "\n".join(parts)


def _friendly_error(message: str) -> str:
    lowered = message.lower()
    if "limit" in lowered:
        return f"Your Claude plan's usage limit was reached: {message}"
    if "login" in lowered or "auth" in lowered:
        return "Claude Code is not logged in. Run `claude` once in a terminal and log in with your Pro account."
    return f"Claude Code error: {message}"
