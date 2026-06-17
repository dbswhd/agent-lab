"""Partial-turn failed-agent retry tests (mock-only).

A partial turn (cursor succeeded, codex errored) should let the user retry ONLY
codex in the same human turn, preserving cursor's reply, flipping status
partial->completed, leaving human_turn invariant, and rejecting
consensus/verified turns.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")

from agent_lab.room_retry import RetryError, _is_consensus_turn, retry_failed_agents


def _write_session(folder: Path, *, turn_profile: str = "team", lines: list[dict] | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "topic.txt").write_text("build X\n", encoding="utf-8")
    (folder / "run.json").write_text(json.dumps({"topic": "build X", "turn_profile": turn_profile}), encoding="utf-8")
    if lines is None:
        lines = [
            {"role": "user", "agent": None, "content": "build X"},
            {"role": "agent", "agent": "cursor", "content": "cursor proposal A", "parallel_round": 1},
            {"role": "system", "agent": "codex", "content": "codex error: timeout", "parallel_round": 1},
        ]
    (folder / "chat.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def _chat(folder: Path) -> list[dict]:
    return [json.loads(x) for x in (folder / "chat.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


# --- consensus detection --------------------------------------------------


@pytest.mark.parametrize(
    "profile,expected",
    [
        ("team", False),
        ("discuss", False),
        ("analyze", False),
        ("divergence", False),
        ("quick", False),
        ("verified", True),
        ("specialist", True),
        ("loop", True),
        ("review", True),
        ("free", True),
    ],
)
def test_is_consensus_turn(profile, expected):
    assert _is_consensus_turn({"turn_profile": profile}) is expected


def test_is_consensus_turn_loop_intent_topology():
    assert _is_consensus_turn({"plan_intent": "loop"}) is True
    assert _is_consensus_turn({"loop_topology": "verified"}) is True
    assert _is_consensus_turn({}) is False


# --- happy path -----------------------------------------------------------


def test_partial_retry_reinvokes_only_failed_and_completes(tmp_path):
    _write_session(tmp_path)
    res = retry_failed_agents(tmp_path, agents=["codex"])
    assert res["status"] == "completed"
    assert res["retried"] == ["codex"]
    assert res["succeeded"] == ["codex"]
    assert res["failed_agents"] == []
    assert res["human_turn"] == 1

    after = _chat(tmp_path)
    # human_turn invariant: still exactly one user message
    assert sum(1 for m in after if m["role"] == "user") == 1
    # cursor reply preserved unchanged, not re-invoked (exactly one cursor agent reply)
    cursor = [m for m in after if m["role"] == "agent" and m["agent"] == "cursor"]
    assert len(cursor) == 1 and cursor[0]["content"] == "cursor proposal A"
    # codex error superseded by an agent reply tagged retry_of_turn
    codex = [m for m in after if m["agent"] == "codex"]
    assert len(codex) == 1 and codex[0]["role"] == "agent"
    assert codex[0].get("retry_of_turn") == 1
    # no lingering system error for codex
    assert not [m for m in after if m["role"] == "system" and m["agent"] == "codex"]
    # retry_history recorded
    hist = json.loads((tmp_path / "run.json").read_text(encoding="utf-8")).get("retry_history")
    assert hist and hist[-1]["agents"] == ["codex"] and hist[-1]["succeeded"] == ["codex"]


def test_partial_retry_default_retries_all_failed(tmp_path):
    _write_session(tmp_path)  # agents=None -> all failed (codex)
    res = retry_failed_agents(tmp_path)
    assert res["status"] == "completed" and res["retried"] == ["codex"]


def test_partial_retry_idempotent_noop_when_nothing_failed(tmp_path):
    _write_session(tmp_path)
    retry_failed_agents(tmp_path, agents=["codex"])  # first: completes
    # second call: last turn now completed -> 409 (not partial)
    with pytest.raises(RetryError) as ei:
        retry_failed_agents(tmp_path, agents=["codex"])
    assert ei.value.code == 409


def test_retry_skips_already_succeeded_agent(tmp_path):
    # request a retry of cursor (already succeeded) on a partial turn -> no-op subset
    _write_session(tmp_path)
    res = retry_failed_agents(tmp_path, agents=["cursor"])
    assert res["retried"] == []
    assert res["status"] == "partial"  # unchanged; codex still failed
    # codex error still present (not touched)
    assert [m for m in _chat(tmp_path) if m["role"] == "system" and m["agent"] == "codex"]


# --- rejections -----------------------------------------------------------


def test_retry_rejects_non_partial_turn(tmp_path):
    # all succeeded -> completed, not partial
    _write_session(
        tmp_path,
        lines=[
            {"role": "user", "agent": None, "content": "build X"},
            {"role": "agent", "agent": "cursor", "content": "ok", "parallel_round": 1},
            {"role": "agent", "agent": "codex", "content": "ok2", "parallel_round": 1},
        ],
    )
    with pytest.raises(RetryError) as ei:
        retry_failed_agents(tmp_path)
    assert ei.value.code == 409


def test_retry_rejects_consensus_turn(tmp_path):
    _write_session(tmp_path, turn_profile="verified")
    with pytest.raises(RetryError) as ei:
        retry_failed_agents(tmp_path)
    assert ei.value.code == 422


# --- context correctness --------------------------------------------------


def test_retried_agent_context_includes_successful_peer(tmp_path):
    from agent_lab.context_bundle import build_context_bundle
    from agent_lab.room_session_persist import load_session_messages

    _write_session(tmp_path)
    messages = load_session_messages(tmp_path)
    bundle = build_context_bundle(
        "build X", messages, "codex", run_meta={"turn_profile": "team"}, parallel_round=2
    ).render()
    # the retried agent (codex) must see cursor's successful reply as this-turn context
    assert "cursor proposal A" in bundle


# --- integration: router endpoint -----------------------------------------


@pytest.mark.integration
def test_retry_agents_endpoint(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from agent_lab.session import SESSIONS_DIR
    from app.server.main import app

    sid = f"test-partial-retry-{uuid.uuid4().hex[:8]}"
    folder = SESSIONS_DIR / sid
    _write_session(folder)
    try:
        client = TestClient(app)
        res = client.post("/api/room/runs/retry-agents", json={"session_id": sid, "agents": ["codex"]})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["ok"] is True and body["status"] == "completed" and body["retried"] == ["codex"]
        # non-partial now -> 409
        res2 = client.post("/api/room/runs/retry-agents", json={"session_id": sid})
        assert res2.status_code == 409
        # unknown session -> 404
        res3 = client.post("/api/room/runs/retry-agents", json={"session_id": "does-not-exist-xyz"})
        assert res3.status_code == 404
    finally:
        import shutil

        shutil.rmtree(folder, ignore_errors=True)
