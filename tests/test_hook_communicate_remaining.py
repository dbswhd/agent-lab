"""Tests for remaining Hook · Communicate items (5–8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.agent_envelope import parse_agent_response_v2, split_structured_envelope_prefix
from agent_lab.agent_hooks_materializer import (
    ensure_session_agent_hooks_from_config,
    native_claude_hooks_overlay,
    native_codex_hooks_overlay,
    native_cursor_hooks_overlay,
)
from agent_lab.agents.registry import call_agent_reply
from agent_lab.structured_envelope_adapter import (
    parse_claude_json_stdout,
    should_request_structured_envelope,
)
from agent_lab.reply_policy import resolve_reply_policy
from agent_lab.run_observability import observability_snapshot
from agent_lab.room_hooks import clear_hooks_config_cache


def test_split_structured_envelope_prefix():
    raw = '{"act":"ENDORSE","refs":["L1"],"confidence":0.9}\n본문입니다'
    structured, body = split_structured_envelope_prefix(raw)
    assert structured is not None
    assert structured["act"] == "ENDORSE"
    assert body == "본문입니다"
    parsed = parse_agent_response_v2(body, structured=structured)
    assert parsed.envelope is not None
    assert parsed.envelope.act == "ENDORSE"


def test_call_agent_reply_mock_structured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_STRUCTURED_ENVELOPE", "1")
    reply = call_agent_reply("codex", "", "hello")
    assert reply.structured_envelope is not None
    assert reply.structured_envelope["act"] == "ENDORSE"


def test_observability_snapshot():
    run = {
        "hook_runs": [{"event": "pre_agent_reply", "agent": "codex"}],
        "turns": [{"communicate_meta": {"envelope_strict": True}}],
    }
    snap = observability_snapshot(run)
    assert snap["hook_run_count"] == 1
    assert snap["last_communicate_meta"]["envelope_strict"] is True


def test_ensure_session_agent_hooks_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    template = tmp_path / "codex-hooks.json"
    template.write_text(
        json.dumps({"version": 1, "hooks": {}}),
        encoding="utf-8",
    )
    cfg = tmp_path / "hooks.toml"
    cfg.write_text(
        f'[agent_hooks]\nenabled = true\ncodex = "{template}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_HOOKS_PATH", str(cfg))
    clear_hooks_config_cache()
    session = tmp_path / "session-1"
    session.mkdir()
    manifest = ensure_session_agent_hooks_from_config(session)
    assert manifest is not None
    assert (session / ".agent-lab/agent-hooks/codex/hooks.json").is_file()
    # idempotent
    again = ensure_session_agent_hooks_from_config(session)
    assert again is not None


def test_native_codex_hooks_overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session = tmp_path / "sess"
    hooks_dir = session / ".agent-lab/agent-hooks/codex"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "hooks.json").write_text('{"version":1}\n', encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("AGENT_LAB_NATIVE_HOOKS", "1")
    with native_codex_hooks_overlay(session, str(workspace)):
        staged = workspace / ".codex/hooks.json"
        assert staged.is_file()
        assert staged.read_text(encoding="utf-8").startswith('{"version":1')
    assert not (workspace / ".codex/hooks.json").is_file()


def test_session_detail_observability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.server.deps import session_detail

    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", tmp_path)
    folder = tmp_path / "sess-obs"
    folder.mkdir()
    (folder / "topic.txt").write_text("t\n", encoding="utf-8")
    (folder / "meta.json").write_text("{}", encoding="utf-8")
    (folder / "run.json").write_text(
        json.dumps(
            {
                "hook_runs": [{"event": "post_harvest", "exit_code": 0}],
                "turns": [{"communicate_meta": {"agent_reply_count": 2}}],
            }
        ),
        encoding="utf-8",
    )
    detail = session_detail("sess-obs")
    assert detail["observability"]["hook_run_count"] == 1
    assert detail["observability"]["last_communicate_meta"]["agent_reply_count"] == 2


def test_native_cursor_hooks_overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session = tmp_path / "sess"
    hooks_dir = session / ".agent-lab/agent-hooks/cursor"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "hooks.json").write_text('{"version":1}\n', encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("AGENT_LAB_NATIVE_HOOKS", "1")
    with native_cursor_hooks_overlay(session, str(workspace)):
        staged = workspace / ".cursor/hooks.json"
        assert staged.is_file()
        assert staged.read_text(encoding="utf-8").startswith('{"version":1')
    assert not (workspace / ".cursor/hooks.json").is_file()


def test_native_claude_hooks_overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session = tmp_path / "sess"
    hooks_dir = session / ".agent-lab/agent-hooks/claude"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "settings.json").write_text(
        json.dumps({"hooks": {"PreToolUse": []}}),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("AGENT_LAB_NATIVE_HOOKS", "1")
    with native_claude_hooks_overlay(session, str(workspace)):
        staged = workspace / ".claude/settings.json"
        assert staged.is_file()
        data = json.loads(staged.read_text(encoding="utf-8"))
        assert "hooks" in data
    assert not (workspace / ".claude/settings.json").is_file()


def test_parse_claude_json_stdout_envelope():
    wrapper = json.dumps(
        {
            "result": '{"act":"ENDORSE","refs":[],"confidence":0.9}\n본문',
        }
    )
    structured, body = parse_claude_json_stdout(wrapper)
    assert structured is not None
    assert structured["act"] == "ENDORSE"
    assert body == "본문"


def test_should_request_structured_envelope_consensus():
    policy = resolve_reply_policy(
        parallel_round=2,
        review_mode=False,
        consensus_mode=True,
        turn_profile="",
        efficiency_mode=False,
    )
    assert should_request_structured_envelope(policy) is True


def test_call_agent_reply_passes_structured_flag(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, bool] = {}

    def _fake_cursor(
        system: str,
        user: str,
        *,
        permissions=None,
        on_activity=None,
        on_bridge_event=None,
        session_folder=None,
        request_structured_envelope=False,
        inbox_mcp=False,
    ):
        captured["structured"] = request_structured_envelope
        return "ok"

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
    monkeypatch.setattr("agent_lab.agents.registry._is_ready", lambda _a: True)
    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _fake_cursor)
    call_agent_reply("cursor", "", "hi", request_structured_envelope=True)
    assert captured.get("structured") is True
