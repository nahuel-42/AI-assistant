import logging
import os

from app.core.config import Settings
from app.services.ai.base import AIProvider, AIProviderError, EchoProvider

log = logging.getLogger(__name__)


def build_provider(settings: Settings) -> AIProvider:
    choice = settings.ai_provider
    if choice == "auto":
        # API key present -> pay-per-use API. Otherwise the user's Claude subscription via Claude Code.
        from app.services.ai.claude_code import find_claude_cli

        if os.environ.get("ANTHROPIC_API_KEY"):
            choice = "claude"
        elif find_claude_cli():
            choice = "claude-code"
        else:
            choice = "claude"  # will report missing credentials when used
        log.info("AI provider auto-selected: %s", choice)

    if choice == "echo":
        return EchoProvider()
    if choice == "claude":
        from app.services.ai.claude import ClaudeProvider

        return ClaudeProvider(model=settings.ai_model, effort=settings.ai_effort)
    if choice == "claude-code":
        from app.services.ai.claude_code import ClaudeCodeProvider, find_claude_cli

        cli = find_claude_cli()
        if not cli:
            raise ValueError("Claude Code CLI not found; install it or set COPILOT_CLAUDE_CODE_PATH")
        return ClaudeCodeProvider(
            cli_path=cli, model=settings.ai_model, effort=settings.ai_effort,
            workdir=settings.data_dir / "claude-code-workdir",
        )
    raise ValueError(f"Unknown AI provider: {settings.ai_provider}")


__all__ = ["AIProvider", "AIProviderError", "EchoProvider", "build_provider"]
