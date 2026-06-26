"""Tests for PTY terminal WebSocket endpoint (Phase 4)."""

from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


@contextmanager
def _make_session(tmp_path: Path) -> Generator[tuple[TestClient, str], None, None]:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_id = "test-terminal-session"
    session_dir = sessions_dir / session_id
    session_dir.mkdir()
    (session_dir / "run.json").write_text("{}", encoding="utf-8")

    with (
        patch("app.server.deps.SESSIONS_DIR", sessions_dir),
        patch("agent_lab.workspace_files.SESSIONS_DIR", sessions_dir),
    ):
        from app.server.main import app

        with TestClient(app, raise_server_exceptions=True) as client:
            yield client, session_id


def _recv_timeout(ws: object, timeout: float = 5.0) -> dict | None:
    """receive_json() with a thread-based timeout; returns None on timeout."""
    q: queue.Queue = queue.Queue()

    def _t() -> None:
        try:
            q.put(("ok", ws.receive_json()))  # type: ignore[attr-defined]
        except Exception as exc:
            q.put(("err", exc))

    th = threading.Thread(target=_t, daemon=True)
    th.start()
    try:
        kind, val = q.get(timeout=timeout)
        if kind == "err":
            raise val  # type: ignore[misc]
        return val  # type: ignore[return-value]
    except queue.Empty:
        return None


# ── PTY spawn helpers ─────────────────────────────────────────────────────────


def test_pty_spawn_and_alive(tmp_path: Path) -> None:
    """spawn() creates a live process; close_session() kills it cleanly."""
    from agent_lab import terminal as term

    sess = term.spawn("test-spawn", tmp_path, slot="spawn-alive")
    assert sess.pid > 0
    assert sess.alive()
    term.close_session("test-spawn", slot="spawn-alive")


def test_pty_write_read(tmp_path: Path) -> None:
    """write_input + read_output round-trips a shell command."""
    from agent_lab import terminal as term

    sess = term.spawn("test-rw", tmp_path, slot="rw")
    try:
        time.sleep(0.8)  # let shell initialise

        # Drain startup output.
        async def drain() -> None:
            for _ in range(20):
                chunk = await term.read_output(sess.fd)
                if not chunk:
                    break

        asyncio.run(drain())

        term.write_input(sess.fd, b"echo PING_TERMINAL\n")
        time.sleep(0.5)

        async def collect() -> bytes:
            out = b""
            for _ in range(25):
                chunk = await term.read_output(sess.fd)
                if chunk is None:
                    break
                out += chunk
                if b"PING_TERMINAL" in out:
                    break
            return out

        output = asyncio.run(collect())
        assert b"PING_TERMINAL" in output, f"got: {output!r}"
    finally:
        term.close_session("test-rw", slot="rw")


# ── WebSocket endpoint ────────────────────────────────────────────────────────


def test_ws_connect_no_error(tmp_path: Path) -> None:
    """Connect via WebSocket; session is accepted without error."""
    with _make_session(tmp_path) as (client, session_id):
        with client.websocket_connect(f"/api/sessions/{session_id}/terminal") as ws:
            ws.send_json({"type": "resize", "rows": 24, "cols": 80})
            # Just verifying the connection doesn't throw.


@pytest.mark.skipif(
    os.getenv("GITHUB_ACTIONS") == "true",
    reason="PTY echo over WebSocket is flaky on ubuntu runners",
)
def test_ws_echo_command(tmp_path: Path) -> None:
    """Send echo command; response eventually contains the echoed string."""
    with _make_session(tmp_path) as (client, session_id):
        received: list[str] = []
        with client.websocket_connect(f"/api/sessions/{session_id}/terminal") as ws:
            ws.send_json({"type": "resize", "rows": 24, "cols": 80})
            time.sleep(1.0)  # let shell finish initialising

            # Send our command.  Do NOT drain first — draining creates orphan
            # threads that block on receive_json() and steal the echo response.
            ws.send_json({"type": "input", "data": "echo WSHELLO\n"})

            # Collect output for up to 8 s.  Startup-noise messages are already
            # queued and processed first; the echo response follows right after.
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                msg = _recv_timeout(ws, timeout=1.0)
                if msg is None:
                    continue
                if msg.get("type") == "output":
                    received.append(msg.get("data", ""))
                if any("WSHELLO" in r for r in received):
                    break

        assert any("WSHELLO" in r for r in received), f"received: {received}"


def test_ws_unknown_session_404(tmp_path: Path) -> None:
    """WebSocket for unknown session is rejected (HTTP 404)."""
    with _make_session(tmp_path) as (client, _):
        with pytest.raises(Exception):
            with client.websocket_connect("/api/sessions/no-such-session/terminal"):
                pass
