import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.audio.pipeline import AudioPipeline
from app.services.audio.segmenter import SAMPLE_RATE, UtteranceSegmenter
from app.services.context.questions import looks_like_question

CHUNK = SAMPLE_RATE // 10  # 100 ms


def tone(seconds: float, amp: float = 0.2) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


def chunks(audio: np.ndarray):
    for i in range(0, len(audio), CHUNK):
        yield audio[i : i + CHUNK]


# ---- segmenter -------------------------------------------------------------

def test_segmenter_splits_on_pauses():
    seg = UtteranceSegmenter()
    stream = np.concatenate([silence(1), tone(1.5), silence(1.2), tone(1.0), silence(1.2)])
    out = [u for c in chunks(stream) for u in seg.feed(c)]
    assert len(out) == 2
    assert 1.5 <= len(out[0]) / SAMPLE_RATE <= 2.8  # speech + pre-roll + trailing silence


def test_segmenter_ignores_clicks_and_force_cuts_long_speech():
    seg = UtteranceSegmenter(max_utterance_s=5)
    clicks = np.concatenate([tone(0.1), silence(1.5)])
    assert [u for c in chunks(clicks) for u in seg.feed(c)] == []
    long = [u for c in chunks(tone(12)) for u in seg.feed(c)]
    assert len(long) == 2 and seg.flush() is not None


# ---- question detection ----------------------------------------------------

@pytest.mark.parametrize("text", [
    "Can you walk me through your last project?",
    "So, tell me about a time you disagreed with a teammate.",
    "Thanks. Walk me through how you'd design a rate limiter",
    "¿Puedes contarme sobre tu experiencia con Python?",
    "Bueno, cuéntame sobre tu último proyecto.",
])
def test_detects_questions(text):
    assert looks_like_question(text)


@pytest.mark.parametrize("text", [
    "Great, thanks.",
    "I worked on the payments team for three years.",
    "Como te decía, el sistema era muy lento.",
    "Okay?",
])
def test_ignores_statements(text):
    assert not looks_like_question(text)


# ---- end to end with fake devices -------------------------------------------

class FakeSource:
    def __init__(self, loopback: bool, audio: np.ndarray, speaker: str | None = None):
        self.speaker = speaker or ("interviewer" if loopback else "user")
        self.kind = "system" if loopback else "mic"
        self.audio = audio

    def run(self, on_chunk, stop: threading.Event, on_device) -> None:
        on_device(f"fake {self.kind}")
        for c in chunks(self.audio):
            if stop.is_set():
                return
            on_chunk(c)
        while not stop.is_set():  # devices keep delivering silence
            on_chunk(silence(0.1))
            time.sleep(0.01)


class FakeTranscriber:
    """Maps utterance length to a scripted line so the test knows what to expect."""

    def load(self) -> None:
        pass

    def transcribe(self, audio: np.ndarray) -> str:
        return "Can you tell me about your last project?" if len(audio) > 2.6 * SAMPLE_RATE else "Sure, happy to."


@pytest.fixture()
def client(tmp_path):
    interviewer = np.concatenate([silence(0.5), tone(2.0), silence(1.5)])
    user = np.concatenate([silence(0.5), tone(1.0), silence(1.5)])

    def factory(mode, on_segment, on_status):
        sources = {
            "both": [FakeSource(False, user), FakeSource(True, interviewer)],
            "system": [FakeSource(True, interviewer)],
            # mic-only hears the whole room, including the question
            "mic": [FakeSource(False, interviewer, speaker="unknown")],
        }[mode]
        return AudioPipeline(sources, FakeTranscriber(), on_segment, on_status)

    app = create_app(Settings(data_dir=tmp_path, ai_provider="echo", tts_enabled=False), audio_factory=factory)
    with TestClient(app) as c:
        yield c


def test_session_transcribes_both_sides_and_auto_suggests(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # initial session.state
        session = client.post("/api/sessions", json={}).json()
        events, deadline = [], time.time() + 10
        # The two sides are transcribed in any order: wait for the answer and both lines.
        while time.time() < deadline:
            events.append(ws.receive_json())
            types = [e["type"] for e in events]
            if "assistant.done" in types and types.count("transcript.segment") >= 2:
                break

    segments = [e["payload"] for e in events if e["type"] == "transcript.segment"]
    by_speaker = {s["speaker"]: s for s in segments}
    assert by_speaker["interviewer"]["is_question"] is True
    assert by_speaker["user"]["text"] == "Sure, happy to." and by_speaker["user"]["is_question"] is False

    statuses = [e["payload"] for e in events if e["type"] == "audio.status"]
    assert any(s["mic"] == "on" and s["system"] == "on" and s["stt"] == "ready" for s in statuses)

    started = next(e["payload"] for e in events if e["type"] == "assistant.started")
    assert started["auto"] is True and started["prompt"] == "Can you tell me about your last project?"

    client.post("/api/sessions/current/stop")
    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert len(detail["transcript"]) == 2 and detail["suggestions"][0]["auto"] is True


def test_pause_stops_capture(client):
    client.post("/api/sessions", json={})
    manager = client.app.state.manager
    assert manager._pipeline is not None
    client.post("/api/sessions/current/pause")
    assert manager._pipeline is None
    client.post("/api/sessions/current/resume")
    assert manager._pipeline is not None
    client.post("/api/sessions/current/stop")
    assert manager._pipeline is None


def collect_until_done(ws, seconds=10):
    events, deadline = [], time.time() + seconds
    while time.time() < deadline:
        events.append(ws.receive_json())
        if events[-1]["type"] == "assistant.done":
            break
    return events


def test_mic_only_mode_answers_questions_heard_by_the_mic(client):
    assert client.put("/api/audio/mode", json={"mode": "mic"}).json() == {"mode": "mic"}
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # session.state
        assert ws.receive_json() == {"type": "audio.mode", "payload": {"mode": "mic"}}
        client.post("/api/sessions", json={})
        events = collect_until_done(ws)
    segments = [e["payload"] for e in events if e["type"] == "transcript.segment"]
    assert [s["speaker"] for s in segments] == ["unknown"] and segments[0]["is_question"]
    assert any(e["type"] == "assistant.started" and e["payload"]["auto"] for e in events)
    statuses = [e["payload"] for e in events if e["type"] == "audio.status"]
    assert all("system" not in s for s in statuses)  # loopback never opened


def test_mode_switch_applies_live_and_is_remembered(client):
    client.post("/api/sessions", json={})
    manager = client.app.state.manager
    first = manager._pipeline
    client.put("/api/audio/mode", json={"mode": "system"})
    assert manager._pipeline is not first and [s.kind for s in manager._pipeline.sources] == ["system"]
    assert manager.preferences.get("capture_mode", "both") == "system"
    assert client.put("/api/audio/mode", json={"mode": "loud"}).status_code == 422
    client.post("/api/sessions/current/stop")


def test_computer_sound_is_ignored_while_reading_aloud(tmp_path):
    """All inputs are muted while the app speaks, so it never answers itself."""
    from tests.test_tts import FakeSpeaker

    interviewer = np.concatenate([silence(0.5), tone(2.0), silence(1.5)])
    user = np.concatenate([silence(0.5), tone(1.0), silence(1.5)])

    def factory(mode, on_segment, on_status):
        return AudioPipeline([FakeSource(False, user), FakeSource(True, interviewer)], FakeTranscriber(), on_segment, on_status)

    app = create_app(Settings(data_dir=tmp_path, ai_provider="echo"), audio_factory=factory, speaker_factory=FakeSpeaker)
    with TestClient(app) as c:
        manager = c.app.state.manager
        manager.speaker.speaking = True  # the app is reading an answer aloud
        session = c.post("/api/sessions", json={}).json()
        time.sleep(4.5)
        c.post("/api/sessions/current/stop")
        speakers = [t["speaker"] for t in c.get(f"/api/sessions/{session['id']}").json()["transcript"]]
    assert speakers == []  # every input is muted while the app speaks, so it never answers itself


def make_app(tmp_path, sources_for_mode):
    def factory(mode, on_segment, on_status):
        return AudioPipeline(sources_for_mode(), FakeTranscriber(), on_segment, on_status)

    return create_app(Settings(data_dir=tmp_path, ai_provider="echo", tts_enabled=False), audio_factory=factory)


def suggestions_after_session(c, seconds=4.5):
    session = c.post("/api/sessions", json={}).json()
    time.sleep(seconds)
    c.post("/api/sessions/current/stop")
    return c.get(f"/api/sessions/{session['id']}").json()


def test_questions_you_ask_are_answered_in_mic_plus_system_mode(tmp_path):
    question = np.concatenate([silence(0.5), tone(2.0), silence(1.5)])  # transcribed as a question
    quiet = silence(4.0)
    app = make_app(tmp_path, lambda: [FakeSource(False, question), FakeSource(True, quiet)])
    with TestClient(app) as c:
        detail = suggestions_after_session(c)
    assert [(t["speaker"], t["is_question"]) for t in detail["transcript"]] == [("user", True)]
    assert len(detail["suggestions"]) == 1 and detail["suggestions"][0]["auto"] is True


def test_same_question_heard_by_mic_and_system_is_answered_once(tmp_path):
    question = np.concatenate([silence(0.5), tone(2.0), silence(1.5)])
    app = make_app(tmp_path, lambda: [FakeSource(False, question), FakeSource(True, question)])
    with TestClient(app) as c:
        detail = suggestions_after_session(c)
    assert sorted(t["speaker"] for t in detail["transcript"]) == ["interviewer", "user"]
    assert len(detail["suggestions"]) == 1


def test_prompt_says_who_asked():
    from app.services.context.manager import InterviewContext

    ctx = InterviewContext()
    assert ctx.build_messages("How are you?", "user")[-1]["content"] == "The user just asked (said aloud): How are you?"
    assert ctx.build_messages("Why?", "interviewer")[-1]["content"].startswith("The interviewer just asked")
    assert "always to help the user" in ctx.build_system()


class StillTalkingSource(FakeSource):
    """Someone who is still mid-sentence: the segmenter never sees the pause that ends it."""

    def run(self, on_chunk, stop: threading.Event, on_device) -> None:
        on_device(f"fake {self.kind}")
        while not stop.is_set():
            on_chunk(tone(0.1))
            time.sleep(0.01)


def test_answer_key_answers_what_was_said_without_a_detected_question(tmp_path):
    statement = np.concatenate([silence(0.5), tone(1.0), silence(1.5)])  # "Sure, happy to."
    app = make_app(tmp_path, lambda: [FakeSource(True, statement)])
    with TestClient(app) as c:
        assert c.post("/api/assistant/answer-now").status_code == 409  # nothing heard yet
        session = c.post("/api/sessions", json={}).json()
        time.sleep(1.5)
        assert c.get(f"/api/sessions/{session['id']}").json()["suggestions"] == []  # not a question
        answer = c.post("/api/assistant/answer-now")
        assert answer.status_code == 202
        assert answer.json()["prompt"] == "Interviewer: Sure, happy to."
        time.sleep(0.5)
        c.post("/api/sessions/current/stop")


def test_answer_key_includes_the_sentence_still_being_spoken(tmp_path):
    app = make_app(tmp_path, lambda: [StillTalkingSource(True, silence(0))])
    with TestClient(app) as c:
        session = c.post("/api/sessions", json={}).json()
        time.sleep(0.4)  # about 4 s of audio, no pause yet, so nothing transcribed on its own
        answer = c.post("/api/assistant/answer-now").json()
        assert answer["prompt"] == "Interviewer: Can you tell me about your last project?"
        time.sleep(0.5)
        c.post("/api/sessions/current/stop")
        detail = c.get(f"/api/sessions/{session['id']}").json()
    assert len(detail["suggestions"]) == 1  # question detection didn't answer it a second time
