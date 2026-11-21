import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.tts.speaker import detect_language, speakable_part


class FakeSpeaker:
    """Records what would be spoken; 'speaks' until stopped."""

    instances: list["FakeSpeaker"] = []

    def __init__(self, on_state):
        self.on_state = on_state
        self.spoken: list[str] = []
        self.speaking = False
        FakeSpeaker.instances.append(self)

    def speak(self, text):
        self.spoken.append(text)
        self.speaking = True
        self.on_state(True)

    def stop(self):
        self.speaking = False
        self.on_state(False)

    def is_speaking(self):
        return self.speaking

    def close(self):
        pass


@pytest.fixture()
def client(tmp_path):
    FakeSpeaker.instances.clear()
    app = create_app(Settings(data_dir=tmp_path, ai_provider="echo", audio_enabled=False), speaker_factory=FakeSpeaker)
    with TestClient(app) as c:
        yield c


def ask_and_wait(client, ws, question):
    client.post("/api/assistant/ask", json={"question": question})
    events = []
    while not events or events[-1]["type"] != "tts.state" or not any(e["type"] == "assistant.done" for e in events):
        events.append(ws.receive_json())
        if len(events) > 200:
            break
    return events


def test_answers_are_read_aloud_and_can_be_stopped(client):
    speaker = FakeSpeaker.instances[0]
    with client.websocket_connect("/ws") as ws:
        initial = [ws.receive_json() for _ in range(3)]  # session.state, audio.mode, tts.state
        assert initial[2] == {"type": "tts.state", "payload": {"available": True, "read_aloud": True, "speaking": False}}
        events = ask_and_wait(client, ws, "What is a deadlock?")
        assert events[-1]["payload"]["speaking"] is True
        assert len(speaker.spoken) == 1 and speaker.spoken[0].endswith("What is a deadlock?")
        client.post("/api/tts/stop")
        assert ws.receive_json() == {"type": "tts.state", "payload": {"available": True, "read_aloud": True, "speaking": False}}


def test_read_aloud_toggle_is_remembered_and_respected(client):
    speaker = FakeSpeaker.instances[0]
    assert client.put("/api/tts", json={"read_aloud": False}).json()["read_aloud"] is False
    assert client.app.state.manager.preferences.get("read_aloud", "true") == "false"
    with client.websocket_connect("/ws") as ws:
        for _ in range(3):
            ws.receive_json()
        client.post("/api/assistant/ask", json={"question": "Hi there"})
        while ws.receive_json()["type"] != "assistant.done":
            pass
    time.sleep(0.05)
    assert speaker.spoken == []


def test_replay_endpoint_speaks_given_text(client):
    client.post("/api/tts/speak", json={"text": "**Short answer.**\n\n- bullet"})
    assert FakeSpeaker.instances[0].spoken == ["Short answer."]


@pytest.mark.parametrize("answer, expected", [
    ('"A process has its own memory; a thread shares it."\n\n- **Memory:** isolated', "A process has its own memory; a thread shares it."),
    ("**Short answer:** use an index.\n- reason one\n- reason two", "Short answer: use an index."),
    ("Line one\nline two\n\n- bullet", "Line one line two"),
    # meta notes are skipped; the sentence to say is read
    ('*(No resume uploaded, so here is a template.)*\n\n"Sure. I profiled it first."\n\n- **Fix:** index',
     "Sure. I profiled it first."),
    # an intro that announces a list reads the list; links keep their text; short asides go
    ("Use this flow:\n\n1. **Context (1 sentence):** it was slow.\n2. **Fix:** used [Redis](http://r) caching.",
     "Use this flow: Context: it was slow. Fix: used Redis caching."),
])
def test_speakable_part(answer, expected):
    assert speakable_part(answer) == expected


def test_speakable_part_caps_length():
    assert speakable_part("word " * 200, max_words=10).endswith("…")


def test_detect_language():
    assert detect_language("Un proceso es un programa en ejecución con su propia memoria.") == "es"
    assert detect_language("A process is a running program with its own memory.") == "en"
