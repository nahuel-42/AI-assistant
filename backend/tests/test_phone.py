import json
import socket
import urllib.parse

import httpx
import pytest
from fastapi.testclient import TestClient
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    settings = Settings(data_dir=tmp_path, ai_provider="echo", audio_enabled=False, tts_enabled=False, phone_port=0)
    with TestClient(create_app(settings)) as c:
        yield c


def phone_events(ws, until: str, limit: int = 50) -> list[dict]:
    events = []
    for _ in range(limit):
        events.append(json.loads(ws.recv(timeout=10)))
        if events[-1]["type"] == until:
            return events
    raise AssertionError(f"no {until} in {events}")


def test_phone_view_is_off_by_default_and_streams_answers_when_on(client):
    state = client.get("/api/phone").json()
    assert state["enabled"] is False and state["mode"] == "wifi" and state["clients"] == 0

    info = client.put("/api/phone", json={"enabled": True}).json()
    assert info["enabled"] and info["qr_image"].startswith("data:image/svg+xml")
    assert "xmlns" in urllib.parse.unquote(info["qr_image"])  # browsers need it to draw the image
    port, token = client.app.state.phone.port, client.app.state.phone.token
    assert info["url"].endswith(f":{port}/?t={token}")
    base = f"http://127.0.0.1:{port}"

    assert httpx.get(f"{base}/?t=wrong").status_code == 403
    page = httpx.get(f"{base}/?t={token}")
    assert page.status_code == 200 and "Interview Copilot" in page.text
    # Only the phone page is exposed on the network, never the main API (profile, controls).
    assert httpx.get(f"{base}/api/profile").status_code == 404
    assert httpx.post(f"{base}/api/sessions").status_code in (404, 405)

    client.post("/api/sessions", json={})
    with connect(f"ws://127.0.0.1:{port}/ws?t={token}") as ws:
        snapshot = json.loads(ws.recv(timeout=10))
        assert snapshot["type"] == "snapshot" and snapshot["payload"]["session"]["status"] == "active"
        assert client.get("/api/phone").json()["clients"] == 1
        client.post("/api/assistant/ask", json={"question": "Why Python?"})
        events = phone_events(ws, "assistant.done")
        types = {e["type"] for e in events}
        assert {"assistant.started", "assistant.delta", "assistant.done"} <= types
        assert not types & {"phone.state", "tts.state", "audio.mode"}  # only interview text
    client.post("/api/sessions/current/stop")


def test_wrong_token_is_rejected_and_new_link_disconnects_old_phones(client):
    client.put("/api/phone", json={"enabled": True})
    phone = client.app.state.phone
    port, old = phone.port, phone.token
    with pytest.raises(Exception):
        with connect(f"ws://127.0.0.1:{port}/ws?t=wrong") as ws:
            ws.recv(timeout=5)

    with connect(f"ws://127.0.0.1:{port}/ws?t={old}") as ws:
        ws.recv(timeout=10)  # snapshot
        client.post("/api/phone/new-link")
        with pytest.raises(ConnectionClosed):
            while True:
                ws.recv(timeout=10)
    assert phone.token != old
    assert httpx.get(f"http://127.0.0.1:{port}/?t={old}").status_code == 403


def test_turning_it_off_closes_the_port_and_is_remembered(tmp_path):
    settings = Settings(data_dir=tmp_path, ai_provider="echo", audio_enabled=False, tts_enabled=False, phone_port=0)
    with TestClient(create_app(settings)) as c:
        c.put("/api/phone", json={"enabled": True})
        port = c.app.state.phone.port
        assert c.put("/api/phone", json={"enabled": False}).json()["enabled"] is False
        with socket.socket() as s:  # the port is free again: nothing listens on the network
            s.bind(("0.0.0.0", port))
        c.put("/api/phone", json={"enabled": True})
    with TestClient(create_app(settings)) as c:  # it was on when the app closed: on again
        assert c.get("/api/phone").json()["enabled"] is True


class FakeTunnel:
    def __init__(self):
        self.url = None
        self.port = None

    @property
    def alive(self):
        return self.url is not None

    async def start(self, exe, port, timeout=40.0):
        self.url, self.port = "https://quiet-fox-example.trycloudflare.com", port
        return self.url

    async def stop(self):
        self.url = None


def test_internet_link_uses_the_tunnel_and_listens_only_on_this_pc(client, tmp_path):
    phone = client.app.state.phone
    state = client.put("/api/phone", json={"mode": "internet", "enabled": True}).json()
    assert state["enabled"] is False and "Download it first" in state["error"]  # no cloudflared yet

    (tmp_path / "bin").mkdir(exist_ok=True)
    (tmp_path / "bin" / "cloudflared.exe").write_bytes(b"fake")
    phone.tunnel = FakeTunnel()
    info = client.put("/api/phone", json={"enabled": True}).json()
    assert info["enabled"] and info["mode"] == "internet" and info["cloudflared"] is True
    assert info["url"] == f"https://quiet-fox-example.trycloudflare.com/?t={phone.token}"
    assert phone.tunnel.port == phone.port  # the tunnel forwards to the phone server
    with pytest.raises(OSError):  # bound to 127.0.0.1: unreachable from the network
        with socket.create_connection((phone_lan_ip(), phone.port), timeout=2):
            pass
    assert httpx.get(f"http://127.0.0.1:{phone.port}/?t={phone.token}").status_code == 200

    back = client.put("/api/phone", json={"mode": "wifi"}).json()  # switching restarts it
    assert back["enabled"] and back["url"].startswith("http://") and phone.tunnel.url is None


def phone_lan_ip():
    from app.services.phone.share import lan_ip

    ip = lan_ip()
    if ip.startswith("127."):
        pytest.skip("no network address on this machine")
    return ip
