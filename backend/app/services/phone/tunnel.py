"""Internet link for the phone view: a Cloudflare quick tunnel (no account, no configuration).

`cloudflared tunnel --url http://127.0.0.1:<port>` gives a random https://*.trycloudflare.com
address that forwards to the local phone server, so a phone on any network (mobile data, a Wi-Fi
that keeps devices apart) can open it. Only the phone server is forwarded, never the main API.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

# Pinned release, verified by the SHA-256 Cloudflare publishes in its release notes.
CLOUDFLARED_VERSION = "2026.10.7"
CLOUDFLARED_URL = (
    f"https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}/cloudflared-windows-amd64.exe"
)
CLOUDFLARED_SHA256 = "2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343"
CLOUDFLARED_SIZE_MB = 55

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
READY_RE = re.compile(r"Registered tunnel connection", re.I)


class TunnelError(Exception):
    pass


def find_cloudflared(bin_dir: Path) -> Path | None:
    override = os.environ.get("COPILOT_CLOUDFLARED")
    for candidate in (override, bin_dir / "cloudflared.exe", shutil.which("cloudflared")):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def install_cloudflared(bin_dir: Path) -> Path:
    """Download the pinned cloudflared and verify its checksum (blocking: run in a thread)."""
    import httpx

    bin_dir.mkdir(parents=True, exist_ok=True)
    target, partial = bin_dir / "cloudflared.exe", bin_dir / "cloudflared.exe.part"
    digest = hashlib.sha256()
    try:
        with httpx.stream("GET", CLOUDFLARED_URL, follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            with partial.open("wb") as f:
                for chunk in response.iter_bytes(1 << 20):
                    digest.update(chunk)
                    f.write(chunk)
    except httpx.HTTPError as exc:
        partial.unlink(missing_ok=True)
        raise TunnelError(f"Download failed: {exc}") from exc
    if digest.hexdigest() != CLOUDFLARED_SHA256:
        partial.unlink(missing_ok=True)
        raise TunnelError("The downloaded file doesn't match Cloudflare's checksum, so it was deleted.")
    partial.replace(target)
    return target


class Tunnel:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self.url: str | None = None

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    async def start(self, exe: Path, port: int, timeout: float = 40.0) -> str:
        """Start the tunnel; returns its public https address once Cloudflare accepts connections."""
        await self.stop()
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            [str(exe), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", creationflags=flags,
        )
        self._proc = proc
        loop = asyncio.get_running_loop()
        found: asyncio.Future[str] = loop.create_future()
        log_tail: list[str] = []

        def read() -> None:  # cloudflared logs to stderr; keep draining it so it never blocks
            url = None
            assert proc.stderr is not None
            for line in proc.stderr:
                log_tail[:] = (log_tail + [line.strip()])[-5:]
                if url is None and (m := URL_RE.search(line)):
                    url = m.group(0)
                if url and READY_RE.search(line) and not found.done():
                    loop.call_soon_threadsafe(lambda u=url: found.done() or found.set_result(u))
            if not found.done():
                loop.call_soon_threadsafe(
                    lambda: found.done() or found.set_exception(TunnelError("Cloudflare tunnel stopped: " + " | ".join(log_tail)))
                )

        threading.Thread(target=read, name="cloudflared-log", daemon=True).start()
        try:
            self.url = await asyncio.wait_for(found, timeout)
        except asyncio.TimeoutError:
            await self.stop()
            raise TunnelError("Cloudflare didn't answer in time. Check the internet connection and try again.") from None
        except TunnelError:
            await self.stop()
            raise
        return self.url

    async def stop(self) -> None:
        proc, self._proc, self.url = self._proc, None, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                await asyncio.to_thread(proc.wait, 5)
            except subprocess.TimeoutExpired:
                proc.kill()
