"""Tests for dev preview auto-probe (M3)."""

from __future__ import annotations

import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent_lab.dev_preview import (
    auto_probe_dev_port,
    dev_server_bg_presets,
    probe_listening_ports,
)


@contextmanager
def _make_session(tmp_path: Path) -> Generator[tuple[TestClient, str], None, None]:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_id = "test-preview-probe"
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


def test_probe_listening_ports_skips_blocked() -> None:
    alive = probe_listening_ports((8765, 5173, 19998))
    assert 8765 not in alive
    assert 5173 not in alive


def test_auto_probe_persists_first_listener(tmp_path: Path) -> None:
    from agent_lab.run_meta import read_run_meta

    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(10)
    port = server.getsockname()[1]
    try:
        with patch(
            "agent_lab.dev_preview.probe_listening_ports",
            return_value=[port],
        ):
            found = auto_probe_dev_port(folder)
        assert found == port
        assert read_run_meta(folder).get("dev_server_port") == port
    finally:
        server.close()


def test_dev_server_presets_include_cwd(tmp_path: Path) -> None:
    presets = dev_server_bg_presets(str(tmp_path))
    assert len(presets) >= 2
    assert all(p["cwd"] == str(tmp_path) for p in presets)
    assert presets[0]["command"]


def test_preview_probe_api(tmp_path: Path) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(10)
    port = server.getsockname()[1]
    try:
        with (
            _make_session(tmp_path) as (client, sid),
            patch(
                "app.server.routers.dev_preview.probe_listening_ports",
                return_value=[port],
            ),
            patch(
                "app.server.routers.dev_preview.auto_probe_dev_port",
                return_value=port,
            ),
        ):
            r = client.post(f"/api/sessions/{sid}/preview/probe")
            assert r.status_code == 200
            data = r.json()
            assert data["port"] == port
            assert data["alive"] is True
            assert port in data["probed"]
    finally:
        server.close()


def test_preview_presets_api(tmp_path: Path) -> None:
    with _make_session(tmp_path) as (client, sid):
        r = client.get(f"/api/sessions/{sid}/preview/presets")
        assert r.status_code == 200
        presets = r.json()["presets"]
        assert isinstance(presets, list)
        assert presets[0]["id"] == "npm-dev"
