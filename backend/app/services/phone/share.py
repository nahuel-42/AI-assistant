"""Phone view: shows the live transcript and answers on a phone on the same network.

Read-only by design. It runs as a second, separate server (bound to the local network) that
only serves the phone page and a filtered event stream, so the main API (profile, sessions,
controls) stays reachable from this PC only. A secret token in the link (shown as a QR code)
keeps other devices on the Wi-Fi out. It runs only while the user has it turned on.

Two ways to reach it: "wifi" (the phone opens this PC's address on the local network) and
"internet" (a Cloudflare quick tunnel, for networks that keep devices apart or mobile data; the
server then listens on 127.0.0.1 only and the tunnel is its single way in).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import socket
from pathlib import Path
from typing import TYPE_CHECKING, Any

import uvicorn
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from app.services.phone.tunnel import (
    CLOUDFLARED_SIZE_MB,
    Tunnel,
    TunnelError,
    find_cloudflared,
    install_cloudflared,
)

if TYPE_CHECKING:
    from app.services.session_manager import SessionManager

log = logging.getLogger(__name__)

PAGE = (Path(__file__).parent / "page.html").read_text(encoding="utf-8")
FORWARDED_EVENTS = {
    "session.state",
    "transcript.segment",
    "assistant.started",
    "assistant.delta",
    "assistant.done",
    "assistant.error",
}
SNAPSHOT_TRANSCRIPT = 40
SNAPSHOT_ANSWERS = 10
MODES = ("wifi", "internet")


def lan_ip() -> str:
    """This PC's address on the local network (no packet is actually sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


class _Server(uvicorn.Server):
    """A uvicorn server living inside the main one's event loop: it must not take over Ctrl+C."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


class PhoneShare:
    def __init__(self, manager: SessionManager, port: int, bin_dir: Path) -> None:
        self.manager = manager
        self.port = port
        self.bin_dir = bin_dir
        prefs = manager.preferences
        mode = prefs.get("phone_mode", "wifi") if prefs else "wifi"
        self.mode = mode if mode in MODES else "wifi"
        self.tunnel = Tunnel()
        self.starting = False
        self.installing = False
        self.token = prefs.get("phone_token", "") if prefs else ""
        if not self.token:
            self._new_token()
        self._server: _Server | None = None
        self._task: asyncio.Task | None = None
        self._clients: set[WebSocket] = set()
        self.error: str | None = None

    # ---- state -----------------------------------------------------------

    @property
    def _serving(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def enabled(self) -> bool:
        return self._serving and (self.mode == "wifi" or self.tunnel.alive)

    @property
    def url(self) -> str | None:
        if self.mode == "internet":
            return f"{self.tunnel.url}/?t={self.token}" if self.tunnel.url else None
        return f"http://{lan_ip()}:{self.port}/?t={self.token}"

    def state(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "clients": len(self._clients),
            "error": self.error,
            "starting": self.starting,
            "cloudflared": find_cloudflared(self.bin_dir) is not None,
            "installing": self.installing,
            "cloudflared_mb": CLOUDFLARED_SIZE_MB,
        }

    def qr_image(self) -> str:
        """The link as a QR code: a complete SVG image as a data URI, ready for <img src>."""
        import segno

        return segno.make(self.url, error="m").svg_data_uri(scale=5, dark="#0f172a", light="#ffffff", border=3)

    async def _publish(self) -> None:
        await self.manager.events.publish("phone.state", self.state())

    def _new_token(self) -> None:
        self.token = secrets.token_urlsafe(16)
        if self.manager.preferences:
            self.manager.preferences.set("phone_token", self.token)

    # ---- control ---------------------------------------------------------

    async def set_enabled(self, enabled: bool) -> dict[str, Any]:
        if enabled:
            await self.start()
        else:
            await self.stop()
        if self.manager.preferences:
            self.manager.preferences.set("phone_enabled", "true" if self.enabled else "false")
        return self.state()

    async def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"Unknown phone mode {mode!r}")
        was_on = self._serving
        if was_on:
            await self.stop()
        self.mode = mode
        if self.manager.preferences:
            self.manager.preferences.set("phone_mode", mode)
        if was_on:
            await self.start()
        else:
            await self._publish()

    async def install(self) -> None:
        """Download cloudflared (pinned version, checksum verified) for the internet link."""
        if self.installing:
            return
        self.installing, self.error = True, None
        await self._publish()
        try:
            await asyncio.to_thread(install_cloudflared, self.bin_dir)
        except TunnelError as exc:
            self.error = str(exc)
        finally:
            self.installing = False
            await self._publish()

    async def start(self) -> None:
        if self.enabled:
            return
        if self._serving:
            await self.stop()
        self.error = None
        exe = find_cloudflared(self.bin_dir) if self.mode == "internet" else None
        if self.mode == "internet" and exe is None:
            self.error = "The internet link needs Cloudflare's tunnel program. Download it first."
            await self._publish()
            return
        # Wi-Fi: listen on the local network. Internet: only the tunnel (on this PC) connects.
        host = "0.0.0.0" if self.mode == "wifi" else "127.0.0.1"
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, self.port))
        except OSError as exc:
            sock.close()
            self.error = f"Port {self.port} is busy ({exc.strerror}). Close the program using it."
            await self._publish()
            return
        self.port = sock.getsockname()[1]  # the real port when 0 (any free port) was asked for
        config = uvicorn.Config(self._build_app(), log_level="warning", lifespan="off", ws_ping_interval=20)
        self._server = _Server(config)
        self._task = asyncio.create_task(self._server.serve(sockets=[sock]))
        if exe is not None:
            self.starting = True
            await self._publish()
            try:
                await self.tunnel.start(exe, self.port)
            except TunnelError as exc:
                self.starting = False
                await self.stop()
                self.error = str(exc)
            self.starting = False
        await self._publish()

    async def stop(self) -> None:
        await self.tunnel.stop()
        server, task = self._server, self._task
        self._server = self._task = None
        for ws in list(self._clients):
            with contextlib.suppress(Exception):
                await ws.close()
        if server and task:
            server.should_exit = True
            with contextlib.suppress(Exception):
                await asyncio.wait_for(task, timeout=5)
        await self._publish()

    async def new_link(self) -> None:
        """Invalidate the old link: phones that had it are disconnected."""
        self._new_token()
        for ws in list(self._clients):
            with contextlib.suppress(Exception):
                await ws.close(code=4403)
        await self._publish()

    # ---- phone server ----------------------------------------------------

    def _authorized(self, token: str) -> bool:
        return bool(token) and secrets.compare_digest(token, self.token)

    def _snapshot(self) -> dict[str, Any]:
        session = self.manager.current
        if not session:
            return {"session": None, "transcript": [], "answers": []}
        transcript = self.manager.transcripts.for_session(session.id)[-SNAPSHOT_TRANSCRIPT:]
        answers = self.manager.suggestions.for_session(session.id)
        answers = sorted(answers, key=lambda s: s.created_at)[-SNAPSHOT_ANSWERS:]
        return {
            "session": session.model_dump(),
            "transcript": [t.model_dump() for t in transcript],
            "answers": [a.model_dump() for a in answers],
        }

    def _build_app(self) -> FastAPI:
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @app.get("/", response_class=HTMLResponse)
        def page(t: str = Query("")) -> HTMLResponse:
            if not self._authorized(t):
                return HTMLResponse(
                    "<h1 style='font-family:sans-serif'>Link expired. Scan the QR code again.</h1>",
                    status_code=403,
                )
            return HTMLResponse(PAGE, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

        @app.websocket("/ws")
        async def stream(websocket: WebSocket, t: str = Query("")) -> None:
            if not self._authorized(t):
                await websocket.close(code=4403)
                return
            await websocket.accept()
            queue = self.manager.events.subscribe()
            self._clients.add(websocket)
            await self._publish()
            try:
                await websocket.send_json({"type": "snapshot", "payload": self._snapshot()})
                receiver = asyncio.create_task(_drain(websocket))
                while not receiver.done():
                    getter = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait({getter, receiver}, return_when=asyncio.FIRST_COMPLETED)
                    if getter in done:
                        event = getter.result()
                        if event["type"] in FORWARDED_EVENTS:
                            await websocket.send_json(event)
                    else:
                        getter.cancel()
            except (WebSocketDisconnect, RuntimeError):
                pass
            finally:
                self.manager.events.unsubscribe(queue)
                self._clients.discard(websocket)
                await self._publish()

        return app


async def _drain(websocket: WebSocket) -> None:
    """Read (and ignore) the phone's keep-alive pings until it disconnects."""
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        while True:
            await websocket.receive_text()
