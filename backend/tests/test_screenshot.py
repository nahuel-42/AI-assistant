import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

SCREEN_TEXT = "1. Two Sum\nGiven an array of integers nums and an integer target...\ndef two_sum(nums, target) :"


def make_client(tmp_path, reader):
    app = create_app(
        Settings(data_dir=tmp_path, ai_provider="echo", audio_enabled=False, tts_enabled=False),
        screen_reader=reader,
    )
    return TestClient(app)


def wait_done(ws):
    while True:
        e = ws.receive_json()
        if e["type"] in ("assistant.done", "assistant.error"):
            return e


def test_screenshot_text_is_saved_added_to_context_and_answered(tmp_path):
    with make_client(tmp_path, lambda: SCREEN_TEXT) as c:
        session = c.post("/api/sessions", json={}).json()
        with c.websocket_connect("/ws") as ws:
            result = c.post("/api/screenshot").json()
            done = wait_done(ws)
        assert result["chars"] == len(SCREEN_TEXT) and result["suggestion_id"]
        # the echo provider repeats the prompt it received: the OCR text is in the context
        assert "<screen_captures>" in done["payload"]["response"] and "Two Sum" in done["payload"]["response"]
        assert "The user just captured their screen" in done["payload"]["response"]

        # a follow-up question still sees the screenshot
        with c.websocket_connect("/ws") as ws:
            c.post("/api/assistant/ask", json={"question": "What is the complexity?"})
            followup = wait_done(ws)
        assert "Two Sum" in followup["payload"]["response"]

        c.post("/api/sessions/current/stop")
        detail = c.get(f"/api/sessions/{session['id']}").json()
    assert detail["transcript"][0]["speaker"] == "screen" and detail["transcript"][0]["text"] == SCREEN_TEXT
    assert detail["suggestions"][0]["auto"] is True


def test_screenshot_works_without_a_session(tmp_path):
    with make_client(tmp_path, lambda: SCREEN_TEXT) as c:
        assert c.post("/api/screenshot").json()["chars"] > 0


def test_empty_screen_and_failures_are_reported(tmp_path):
    with make_client(tmp_path, lambda: "  ") as c:
        assert c.post("/api/screenshot").json() == {"chars": 0, "text": "", "suggestion_id": None}

    def broken():
        raise RuntimeError("no display")

    with make_client(tmp_path, broken) as c:
        r = c.post("/api/screenshot")
        assert r.status_code == 409 and "no display" in r.json()["detail"]


def test_only_the_last_three_screens_are_kept():
    from app.services.context.manager import InterviewContext

    ctx = InterviewContext()
    for i in range(5):
        ctx.add_screen(f"screen {i}")
    content = ctx.build_messages("q")[-1]["content"]
    assert "screen 0" not in content and "screen 1" not in content and "screen 4" in content
