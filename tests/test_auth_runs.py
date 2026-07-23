from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import anyio
import pytest


@pytest.fixture(autouse=True)
def mock_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")


def _wait_for_terminal(run: object, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while getattr(run, "status") == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert getattr(run, "status") != "running"


def test_auth_run_streams_output_and_completion() -> None:
    from agent_lab.auth_runs import drain_auth_events, get_auth_run, start_auth_run

    reference = start_auth_run("codex")
    run = get_auth_run(reference["id"])
    assert run is not None
    _wait_for_terminal(run)
    events = drain_auth_events(run)
    assert any(event["type"] == "output" for event in events)
    assert events[-1]["type"] == "completed"


def test_format_auth_slash_summary_extracts_cli_phrase() -> None:
    from agent_lab.auth_runs import format_auth_slash_summary

    summary = format_auth_slash_summary(
        "claude",
        "login",
        terminal="completed",
        output="Opening browser…\nLogin successful\n",
    )
    assert summary == "/login claude: Login successful"


def test_auth_run_emits_slash_result_to_session(tmp_path: Path) -> None:
    import json

    from agent_lab.auth_runs import get_auth_run, start_auth_run

    chat = tmp_path / "chat.jsonl"
    chat.write_text("", encoding="utf-8")
    reference = start_auth_run("codex", "login", session_folder=tmp_path)
    run = get_auth_run(reference["id"])
    assert run is not None
    _wait_for_terminal(run)
    lines = chat.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["role"] == "system"
    assert "/login codex:" in payload["content"]
    assert "시작" not in payload["content"]
    assert "complete" in payload["content"].lower()


def test_auth_run_rejects_unknown_provider() -> None:
    from agent_lab.auth_runs import start_auth_run

    with pytest.raises(RuntimeError, match="unknown provider"):
        start_auth_run("not-registered")


def test_auth_run_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.auth_runs as auth_runs

    monkeypatch.setattr(
        auth_runs,
        "_resolved_argv",
        lambda spec, action: [sys.executable, "-c", "import time; time.sleep(5)"],
    )
    reference = auth_runs.start_auth_run("codex")
    run = auth_runs.get_auth_run(reference["id"])
    assert run is not None
    auth_runs.cancel_auth_run(run)
    _wait_for_terminal(run)
    assert auth_runs.drain_auth_events(run)[-1]["type"] == "cancelled"


def test_auth_run_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.auth_runs as auth_runs

    monkeypatch.setattr(
        auth_runs,
        "_resolved_argv",
        lambda spec, action: [sys.executable, "-c", "raise SystemExit(4)"],
    )
    reference = auth_runs.start_auth_run("claude")
    run = auth_runs.get_auth_run(reference["id"])
    assert run is not None
    _wait_for_terminal(run)
    assert auth_runs.drain_auth_events(run)[-1]["type"] == "failed"


def test_auth_url_allowlist() -> None:
    from agent_lab.auth_runs import _safe_auth_url
    from agent_lab.provider_registry import get_provider

    codex = get_provider("codex")
    assert codex is not None
    assert _safe_auth_url(codex, "https://auth.openai.com/oauth/start") is not None
    assert _safe_auth_url(codex, "https://openai.com.evil.test/oauth") is None
    assert _safe_auth_url(codex, "http://auth.openai.com/oauth") is None


def test_provider_status_api_is_readonly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    import agent_lab.app_config as app_config
    from app.server.main import app

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path)
    response = TestClient(app).get("/api/auth/providers")
    assert response.status_code == 200
    providers = response.json()["providers"]
    assert {row["id"] for row in providers} >= {"cursor", "claude", "codex"}
    assert all(row["state"] in {"logged_in", "logged_out", "unavailable", "checking", "error"} for row in providers)
    assert all(row["account_mode"] in {"ambient", "profile_slots", "api_chain"} for row in providers)


def test_login_command_returns_auth_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import auth_runs
    from agent_lab.command_registry import execute_command

    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "0")
    monkeypatch.setattr(auth_runs, "provider_login_status", lambda _pid: ("logged_out", None))
    chat = tmp_path / "chat.jsonl"
    chat.write_text("", encoding="utf-8")
    result = execute_command(tmp_path, "login", args="oauth codex", workspace=tmp_path)
    assert result["ok"] is True
    auth_run = result["result"]["auth_run"]
    assert auth_run["provider_id"] == "codex"
    assert auth_run["action"] == "login"
    assert chat.read_text(encoding="utf-8").strip() == ""
    run = auth_runs.get_auth_run(auth_run["id"])
    assert run is not None
    _wait_for_terminal(run)
    assert "/login codex:" in chat.read_text(encoding="utf-8")
    assert "시작" not in chat.read_text(encoding="utf-8")


def test_login_command_skips_when_already_logged_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab import auth_runs
    from agent_lab.command_registry import execute_command

    monkeypatch.setenv("AGENT_LAB_DYNAMIC_ROOM", "0")
    monkeypatch.setattr(auth_runs, "provider_login_status", lambda _pid: ("logged_in", "already"))
    result = execute_command(tmp_path, "login", args="oauth claude", workspace=tmp_path)
    assert result["ok"] is True
    assert "auth_run" not in result["result"]
    assert "이미 로그인" in result["text"]


def test_auth_run_websocket_delivers_terminal_event() -> None:
    from fastapi.testclient import TestClient

    from agent_lab.auth_runs import start_auth_run
    from app.server.main import app

    reference = start_auth_run("codex")
    with TestClient(app).websocket_connect(f"/api/auth/runs/{reference['id']}") as ws:
        event_types: list[str] = []
        while "completed" not in event_types:
            event_types.append(ws.receive_json()["type"])
    assert "output" in event_types
    assert event_types[-1] == "completed"


def test_auth_run_websocket_sends_normal_close() -> None:
    from agent_lab.auth_runs import get_auth_run, start_auth_run
    from app.server.routers.auth import auth_run_ws

    class FakeWebSocket:
        def __init__(self) -> None:
            self.events: list[dict[str, Any]] = []
            self.close_codes: list[int] = []

        async def accept(self) -> None:
            return None

        async def send_json(self, event: dict[str, Any]) -> None:
            self.events.append(event)

        async def receive_json(self) -> dict[str, Any]:
            await anyio.sleep(1)
            return {}

        async def close(self, code: int) -> None:
            self.close_codes.append(code)

    reference = start_auth_run("codex")
    run = get_auth_run(reference["id"])
    assert run is not None
    _wait_for_terminal(run)
    ws = FakeWebSocket()
    anyio.run(auth_run_ws, ws, reference["id"])
    assert ws.close_codes == [1000]


def test_api_login_secret_is_redacted_from_command_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.app_config as app_config
    from agent_lab.command_registry import execute_command
    from agent_lab.run.meta import read_run_meta

    monkeypatch.setattr(app_config, "config_dir", lambda: tmp_path / "config")
    secret = "sk-masked-history-1234"
    result = execute_command(tmp_path, "login", args=f"api kimi {secret}", workspace=tmp_path)
    assert result["ok"] is True
    history = read_run_meta(tmp_path)["command_history"]
    assert secret not in str(history)
    assert history[-1]["args"] == "[redacted]"


def test_command_catalog_cold_start_does_not_wait_for_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agent_lab.plugin_discovery as discovery
    from agent_lab.command_registry import list_commands

    def slow_discovery(workspace: Path, *, mock: bool) -> dict[str, object]:
        time.sleep(0.4)
        return {
            "workspace": str(workspace),
            "mock": mock,
            "agents": {"cursor": [], "codex": [], "claude": []},
            "plugins": [],
        }

    discovery.reset_plugin_discovery_cache()
    monkeypatch.setattr(discovery, "_discover_plugins_uncached", slow_discovery)
    started = time.monotonic()
    payload = list_commands(tmp_path, workspace=tmp_path)
    elapsed = time.monotonic() - started
    assert elapsed < 0.1
    assert payload["discovery_refreshing"] is True
    assert any(row["id"] == "goal-check" for row in payload["commands"])


def test_status_revalidation_discards_probe_started_before_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent_lab.auth_runs as auth_runs

    first_probe_started = threading.Event()
    release_first_probe = threading.Event()
    probe_count = 0

    def probe(spec: object) -> tuple[str, str]:
        nonlocal probe_count
        probe_count += 1
        if probe_count == 1:
            first_probe_started.set()
            release_first_probe.wait(timeout=1)
            return "logged_out", "stale"
        return "logged_in", "current"

    monkeypatch.setattr(auth_runs, "_probe_provider_status", probe)
    with auth_runs._status_lock:
        auth_runs._status_cache.pop("codex", None)
        auth_runs._status_refreshing.discard("codex")
        auth_runs._status_generation["codex"] = 0

    auth_runs.refresh_provider_status("codex")
    assert first_probe_started.wait(timeout=1)
    auth_runs.revalidate_provider_status("codex")
    try:
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            with auth_runs._status_lock:
                cached = auth_runs._status_cache.get("codex")
            if cached and cached[1] == "logged_in":
                break
            time.sleep(0.01)
        else:
            pytest.fail("post-login status probe did not publish its result")
    finally:
        release_first_probe.set()

    time.sleep(0.02)
    with auth_runs._status_lock:
        assert auth_runs._status_cache["codex"][1:] == ("logged_in", "current")


def test_interpret_cursor_status_not_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.auth_runs as auth_runs
    from agent_lab.provider_registry import get_provider

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    spec = get_provider("cursor")
    assert spec is not None
    result = subprocess.CompletedProcess(
        args=["cursor-agent", "status"],
        returncode=0,
        stdout="Not logged in\n",
        stderr="",
    )
    state, detail = auth_runs._interpret_cli_status(spec, result)
    assert state == "logged_out"
    assert "Not logged in" in (detail or "")


def test_interpret_claude_status_logged_out_with_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.auth_runs as auth_runs
    from agent_lab.provider_registry import get_provider

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    spec = get_provider("claude")
    assert spec is not None
    result = subprocess.CompletedProcess(
        args=["claude", "auth", "status"],
        returncode=0,
        stdout='{"loggedIn": false, "authMethod": "none", "apiProvider": "firstParty"}\n',
        stderr="",
    )
    state, detail = auth_runs._interpret_cli_status(spec, result)
    assert state == "logged_out"
    assert detail == "OAuth 미로그인 — /login 또는 claude auth login"
    assert "loggedIn" not in (detail or "")


def test_format_claude_auth_status_detail() -> None:
    from agent_lab.claude.cli import format_claude_auth_status_detail

    logged_out = '{"loggedIn": false, "authMethod": "none", "apiProvider": "firstParty"}'
    assert "OAuth 미로그인" in format_claude_auth_status_detail(logged_out, logged_in=False)
    logged_in = '{"loggedIn": true, "email": "user@example.com"}'
    assert format_claude_auth_status_detail(logged_in, logged_in=True) == "OAuth 연결됨 (user@example.com)"


def test_revalidate_claude_invalidates_auth_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.auth_runs as auth_runs
    import agent_lab.claude.cli as claude_cli

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    claude_cli._AUTH_STATUS_CACHE = (0.0, False, "stale")
    auth_runs.revalidate_provider_status("claude")
    assert claude_cli._AUTH_STATUS_CACHE is None


def test_probe_claude_status_uses_claude_bin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import agent_lab.auth_runs as auth_runs
    from agent_lab.provider_registry import get_provider

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    fake_bin = tmp_path / "claude"
    fake_bin.write_text('#!/bin/sh\necho \'{"loggedIn": false, "authMethod": "none"}\'\n', encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))

    seen: list[list[str]] = []

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout='{"loggedIn": false}\n', stderr="")

    monkeypatch.setattr(auth_runs.subprocess, "run", fake_run)
    spec = get_provider("claude")
    assert spec is not None
    state, _ = auth_runs._probe_provider_status(spec)
    assert state == "logged_out"
    assert seen and seen[0][0] == str(fake_bin.resolve())


def test_provider_login_status_cursor_not_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.auth_runs as auth_runs

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    # CI runners often lack cursor-agent on PATH; stub resolve so status probes run.
    monkeypatch.setattr(
        auth_runs,
        "_resolve_provider_executable",
        lambda _spec: "/usr/bin/cursor-agent",
    )

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(argv, 0, stdout="Not logged in\n", stderr="")

    monkeypatch.setattr(auth_runs.subprocess, "run", fake_run)
    state, _ = auth_runs.provider_login_status("cursor")
    assert state == "logged_out"
