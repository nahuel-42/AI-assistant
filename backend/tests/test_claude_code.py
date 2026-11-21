"""Exercises ClaudeCodeProvider against a fake `claude` executable (a Python script)."""

import asyncio
import json
import sys
import textwrap

import pytest

from app.services.ai.base import AIProviderError
from app.services.ai.claude_code import ClaudeCodeProvider, _flatten

FAKE_CLI = textwrap.dedent('''
    import json, os, sys
    prompt = sys.stdin.read()
    args = sys.argv[1:]
    system = open(args[args.index("--system-prompt-file") + 1], encoding="utf-8").read()
    def out(e): print(json.dumps(e), flush=True)
    out({"type": "system", "subtype": "init", "apiKeySource": "none"})
    if "FAIL" in prompt:
        out({"type": "result", "subtype": "error", "is_error": True, "result": "Claude AI usage limit reached"})
        sys.exit(1)
    out({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "unifiedWindows": {"five_hour": {"utilization": 0.4}}}})
    leaked = "KEY-LEAKED" if os.environ.get("ANTHROPIC_API_KEY") else "no-key"
    for chunk in [leaked, " | ", system[:6], " | ", prompt.splitlines()[-1]]:
        out({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": chunk}}})
    out({"type": "result", "subtype": "success", "is_error": False, "result": "done"})
''')


@pytest.fixture()
def provider(tmp_path, monkeypatch):
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE_CLI, encoding="utf-8")
    launcher = tmp_path / ("fake_claude.cmd" if sys.platform == "win32" else "fake_claude")
    if sys.platform == "win32":
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    else:
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        launcher.chmod(0o755)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-reach-child")
    return ClaudeCodeProvider(str(launcher), "claude-opus-5-5", "low", tmp_path / "work")


async def collect(provider, messages):
    return "".join([t async for t in provider.stream_answer("SYSTEM prompt", messages)])


def test_streams_text_without_api_key(provider):
    text = asyncio.run(collect(provider, [{"role": "user", "content": "Question to answer: hi"}]))
    assert text == "no-key | SYSTEM | Question to answer: hi"
    assert provider.last_rate_limit["unifiedWindows"]["five_hour"]["utilization"] == 0.4
    assert list((provider.workdir).glob("copilot-system-*")) == []  # temp prompt file cleaned up


def test_reports_plan_limit_errors(provider):
    with pytest.raises(AIProviderError, match="usage limit"):
        asyncio.run(collect(provider, [{"role": "user", "content": "FAIL"}]))


def test_flatten_includes_history():
    text = _flatten([
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Question to answer: Q2"},
    ])
    assert "Question: Q1" in text and "Your suggestion: A1" in text and text.endswith("Q2")
