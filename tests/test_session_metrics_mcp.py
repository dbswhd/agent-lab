from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.cursor.session_metrics_mcp import (
    SESSION_METRICS_MCP_SERVER_NAME,
    build_codex_session_metrics_config_args,
    build_session_metrics_mcp_servers,
    merge_room_mcp_servers,
    session_metrics_mcp_enabled,
    session_metrics_mcp_stdio_spec,
)
from agent_lab.session.metrics_payload import (
    build_emergence_kpis_payload,
    build_session_metrics_payload,
    build_turn_policy_snapshot,
)


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "chat.jsonl").write_text(
        json.dumps(
            {
                "role": "human",
                "content": "hello",
                "turn": 1,
                "ts": "2026-06-28T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "status": "running",
                "turn_policy": {"enabled": True, "effects": {"scribe": True}},
                "consensus": {"recombination": {"skipped": "efficiency_mode"}},
            }
        ),
        encoding="utf-8",
    )
    return folder


def test_session_metrics_payload(session_dir: Path) -> None:
    payload = build_session_metrics_payload(session_dir)
    assert payload["session_id"] == session_dir.name
    assert "emergence_counts" in payload
    assert payload["turn_policy"]["turn_policy"]["enabled"] is True


def test_emergence_kpis_and_turn_policy_snapshot(session_dir: Path) -> None:
    kpis = build_emergence_kpis_payload(session_dir)
    assert isinstance(kpis, dict)
    assert "scores" in kpis
    from agent_lab.run.meta import read_run_meta

    snap = build_turn_policy_snapshot(read_run_meta(session_dir))
    assert snap["turn_policy"]["enabled"] is True


def test_session_metrics_mcp_stdio_spec(session_dir: Path) -> None:
    spec = session_metrics_mcp_stdio_spec(session_dir)
    assert spec["command"]
    assert "metrics_mcp_server" in " ".join(spec["args"])
    assert spec["env"]["AGENT_LAB_SESSION_FOLDER"] == str(session_dir)


def test_build_session_metrics_mcp_servers(session_dir: Path) -> None:
    servers = build_session_metrics_mcp_servers(session_dir)
    assert SESSION_METRICS_MCP_SERVER_NAME in servers
    assert servers[SESSION_METRICS_MCP_SERVER_NAME].command


def test_merge_room_mcp_servers() -> None:
    a = {"inbox": {"command": "x"}}
    b = {"session_metrics": {"command": "y"}}
    merged = merge_room_mcp_servers(a, b)
    assert merged == {"inbox": {"command": "x"}, "session_metrics": {"command": "y"}}


def test_build_codex_session_metrics_config_args(session_dir: Path) -> None:
    args = build_codex_session_metrics_config_args(session_dir)
    joined = " ".join(args)
    assert SESSION_METRICS_MCP_SERVER_NAME in joined
    assert "enabled=true" in joined


def test_session_metrics_mcp_enabled_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_SESSION_METRICS_MCP", raising=False)
    assert session_metrics_mcp_enabled() is True
    monkeypatch.setenv("AGENT_LAB_SESSION_METRICS_MCP", "0")
    assert session_metrics_mcp_enabled() is False
