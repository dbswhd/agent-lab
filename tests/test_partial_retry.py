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
from agent_lab.room.retry import (
    RetryError,
    _failure_signature,
    _is_consensus_turn,
    diagnosis_line,
    handle_retry_diagnosis_inbox_resolve,
    retry_failed_agents,
)
from agent_lab.run.meta import read_run_meta

os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")


@pytest.fixture(autouse=True)
def _force_mock_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    """xdist workers can lose MOCK_AGENTS via other tests that pop it."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")


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
    from agent_lab.context.bundle import build_context_bundle
    from agent_lab.room.session_persist import load_session_messages

    _write_session(tmp_path)
    messages = load_session_messages(tmp_path)
    bundle = build_context_bundle(
        "build X", messages, "codex", run_meta={"turn_profile": "team"}, parallel_round=2
    ).render()
    # the retried agent (codex) must see cursor's successful reply as this-turn context
    assert "cursor proposal A" in bundle


# --- integration: router endpoint -----------------------------------------


@pytest.mark.integration
def test_retry_agents_endpoint(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import agent_lab.session as session_mod

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    from app.server.main import app

    sid = f"test-partial-retry-{uuid.uuid4().hex[:8]}"
    folder = tmp_path / sid
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


# --- C1: diagnose-before-retry (docs/N10-USER-LOOP-WISDOM-DRAFT.md §4-C1) --


def test_failure_signature_deterministic_and_order_independent():
    a = _failure_signature(["codex", "cursor"], {"codex": "timeout", "cursor": "oom"})
    b = _failure_signature(["cursor", "codex"], {"codex": "timeout", "cursor": "oom"})
    assert a == b
    c = _failure_signature(["codex", "cursor"], {"codex": "different error", "cursor": "oom"})
    assert a != c


def test_diagnosis_line_renders_one_line_per_agent():
    line = diagnosis_line(["codex"], {"codex": "codex error: timeout\nstack trace..."})
    assert line == "codex: codex error: timeout"


def test_diagnosis_line_empty_for_no_agents():
    assert diagnosis_line([], {}) == ""


def _seed_prior_retry_signature(folder: Path, *, turn: int, agents: list[str], errors: dict[str, str]) -> str:
    sig = _failure_signature(agents, errors)
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    run["retry_history"] = [{"turn": turn, "agents": agents, "succeeded": [], "ts": "prior", "signature": sig}]
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    return sig


def test_retry_blocks_same_signature_repeat_and_escalates_inbox(tmp_path):
    _write_session(tmp_path)
    sig = _seed_prior_retry_signature(tmp_path, turn=1, agents=["codex"], errors={"codex": "codex error: timeout"})

    with pytest.raises(RetryError) as ei:
        retry_failed_agents(tmp_path, agents=["codex"])
    assert ei.value.code == 409
    assert "codex" in ei.value.message

    items = read_run_meta(tmp_path).get("human_inbox") or []
    assert len(items) == 1
    assert items[0]["kind"] == "retry_diagnosis"
    assert items[0]["refs"][0] == "1"
    assert items[0]["refs"][1] == sig
    assert items[0]["status"] == "pending"


def test_retry_block_does_not_duplicate_pending_inbox_item(tmp_path):
    _write_session(tmp_path)
    _seed_prior_retry_signature(tmp_path, turn=1, agents=["codex"], errors={"codex": "codex error: timeout"})

    for _ in range(2):
        with pytest.raises(RetryError):
            retry_failed_agents(tmp_path, agents=["codex"])

    items = read_run_meta(tmp_path).get("human_inbox") or []
    assert len(items) == 1


def test_retry_force_bypasses_same_signature_block(tmp_path):
    _write_session(tmp_path)
    _seed_prior_retry_signature(tmp_path, turn=1, agents=["codex"], errors={"codex": "codex error: timeout"})

    res = retry_failed_agents(tmp_path, agents=["codex"], force=True)
    assert res["status"] == "completed"
    # force bypassed the guard entirely — no escalation needed
    assert (read_run_meta(tmp_path).get("human_inbox") or []) == []


def test_retry_diagnosis_inbox_approve_then_retry_bypasses_once(tmp_path):
    _write_session(tmp_path)
    _seed_prior_retry_signature(tmp_path, turn=1, agents=["codex"], errors={"codex": "codex error: timeout"})

    with pytest.raises(RetryError):
        retry_failed_agents(tmp_path, agents=["codex"])

    items = read_run_meta(tmp_path).get("human_inbox") or []
    handle_retry_diagnosis_inbox_resolve(tmp_path, items[0], selected=["approve"], status="resolved")

    ack = read_run_meta(tmp_path).get("retry_force_ack")
    assert ack and ack["turn"] == 1

    res = retry_failed_agents(tmp_path, agents=["codex"])
    assert res["status"] == "completed"
    # one-time ack consumed regardless of outcome
    assert read_run_meta(tmp_path).get("retry_force_ack") is None


def test_retry_diagnosis_inbox_reject_does_not_ack(tmp_path):
    _write_session(tmp_path)
    _seed_prior_retry_signature(tmp_path, turn=1, agents=["codex"], errors={"codex": "codex error: timeout"})

    with pytest.raises(RetryError):
        retry_failed_agents(tmp_path, agents=["codex"])

    items = read_run_meta(tmp_path).get("human_inbox") or []
    handle_retry_diagnosis_inbox_resolve(tmp_path, items[0], selected=["reject"], status="resolved")

    assert read_run_meta(tmp_path).get("retry_force_ack") is None
    with pytest.raises(RetryError):
        retry_failed_agents(tmp_path, agents=["codex"])


def test_retry_history_records_signature(tmp_path):
    _write_session(tmp_path)
    retry_failed_agents(tmp_path, agents=["codex"])
    hist = read_run_meta(tmp_path).get("retry_history")
    assert hist and "signature" in hist[-1]
