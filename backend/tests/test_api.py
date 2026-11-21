import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, ai_provider="echo", audio_enabled=False, tts_enabled=False))
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "provider": "echo", "audio": False, "stt_model": None}


def test_session_lifecycle(client):
    assert client.get("/api/sessions/current").json() is None

    started = client.post("/api/sessions", json={"title": "Acme backend"}).json()
    assert started["status"] == "active"
    assert client.post("/api/sessions", json={}).status_code == 409  # only one live session

    assert client.post("/api/sessions/current/pause").json()["status"] == "paused"
    assert client.post("/api/sessions/current/pause").status_code == 409
    assert client.post("/api/sessions/current/resume").json()["status"] == "active"

    stopped = client.post("/api/sessions/current/stop").json()
    assert stopped["status"] == "stopped" and stopped["ended_at"]
    assert client.get("/api/sessions/current").json() is None
    assert [s["id"] for s in client.get("/api/sessions").json()] == [started["id"]]


def test_ask_streams_over_websocket_and_is_stored(client):
    session = client.post("/api/sessions", json={}).json()
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "session.state"
        suggestion = client.post("/api/assistant/ask", json={"question": "Tell me about yourself"}).json()

        events = []
        while not events or events[-1]["type"] not in ("assistant.done", "assistant.error"):
            event = ws.receive_json()
            if event["type"].startswith("assistant."):
                events.append(event)

    assert events[0]["type"] == "assistant.started"
    assert any(e["type"] == "assistant.delta" for e in events)
    assert events[-1]["type"] == "assistant.done"
    assert "Tell me about yourself" in events[-1]["payload"]["response"]

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["suggestions"][0]["id"] == suggestion["id"]
    assert detail["suggestions"][0]["status"] == "done"


def test_delete_session(client):
    session = client.post("/api/sessions", json={}).json()
    assert client.delete(f"/api/sessions/{session['id']}").status_code == 409
    client.post("/api/sessions/current/stop")
    assert client.delete(f"/api/sessions/{session['id']}").status_code == 204
    assert client.get(f"/api/sessions/{session['id']}").status_code == 404
