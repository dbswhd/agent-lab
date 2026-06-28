"""Tests for dev preview port management API."""

from __future__ import annotations

import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ── Helpers ──────────────────────────────────────────────────────────────────


@contextmanager
def _make_session(tmp_path: Path) -> Generator[tuple[TestClient, str], None, None]:
    """Spin up a TestClient with a throwaway session directory."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    session_id = "test-preview-session"
    session_dir = sessions_dir / session_id
    session_dir.mkdir()
    (session_dir / "run.json").write_text("{}", encoding="utf-8")

    with (
        patch("app.server.deps.SESSIONS_DIR", sessions_dir),
        patch("agent_lab.workspace.files.SESSIONS_DIR", sessions_dir),
    ):
        from app.server.main import app

        with TestClient(app, raise_server_exceptions=True) as client:
            yield client, session_id


# ── Port management ───────────────────────────────────────────────────────────


def test_status_no_port(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.get(f"/api/sessions/{sid}/preview/status")
        assert r.status_code == 200
        data = r.json()
        assert data["port"] is None
        assert data["alive"] is False


def test_set_port_and_status(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.put(
            f"/api/sessions/{sid}/preview/port",
            json={"port": 3000},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["port"] == 3000
        # alive depends on whether something is running on 3000 — just check key exists
        assert "alive" in data

        # Status should now return the stored port
        r2 = client.get(f"/api/sessions/{sid}/preview/status")
        assert r2.status_code == 200
        assert r2.json()["port"] == 3000


def test_clear_port(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        client.put(f"/api/sessions/{sid}/preview/port", json={"port": 3000})
        r = client.delete(f"/api/sessions/{sid}/preview/port")
        assert r.status_code == 200
        assert r.json()["port"] is None

        r2 = client.get(f"/api/sessions/{sid}/preview/status")
        assert r2.json()["port"] is None


# ── Port validation ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("port", [8765, 5173, 5174, 5175])
def test_blocked_ports_rejected(tmp_path: Path, port: int) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.put(
            f"/api/sessions/{sid}/preview/port",
            json={"port": port},
        )
        assert r.status_code == 422
        assert "reserved" in r.json()["detail"].lower()


@pytest.mark.parametrize("port", [0, 1023, 65535, 99999])
def test_out_of_range_ports_rejected(tmp_path: Path, port: int) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.put(
            f"/api/sessions/{sid}/preview/port",
            json={"port": port},
        )
        assert r.status_code == 422


# ── is_port_listening ────────────────────────────────────────────────────────


def test_port_alive_when_listening(tmp_path: Path) -> None:
    """Start a dummy TCP listener and confirm alive=True."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(10)
    port = server.getsockname()[1]
    try:
        with _make_session(tmp_path) as (client, sid):
            r = client.put(
                f"/api/sessions/{sid}/preview/port",
                json={"port": port},
            )
            assert r.status_code == 200
            assert r.json()["alive"] is True

            r2 = client.get(f"/api/sessions/{sid}/preview/status")
            assert r2.json()["alive"] is True
    finally:
        server.close()


def test_port_not_alive_when_nothing_listening(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.put(
            f"/api/sessions/{sid}/preview/port",
            json={"port": 19999},
        )
        assert r.status_code == 200
        assert r.json()["alive"] is False


# ── Session validation ────────────────────────────────────────────────────────


def test_unknown_session_404(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, _sid):
        r = client.get("/api/sessions/no-such-session/preview/status")
        assert r.status_code == 404
