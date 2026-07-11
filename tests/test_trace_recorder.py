"""Tests for the OTel-lite span tracer (G5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_lab.run.observability import observability_snapshot, trace_tail
from agent_lab.trace_recorder import TraceRecorder, install_tracer, record_control_span


def _spans(folder: Path) -> list[dict[str, Any]]:
    path = folder / "trace.jsonl"
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def test_agent_span_recorded_with_duration(tmp_path: Path) -> None:
    rec = TraceRecorder(tmp_path, {}, None, human_turn=1)
    rec("agent_start", {"agent": "claude", "round": 1})
    rec("agent_done", {"agent": "claude", "round": 1})
    spans = _spans(tmp_path)
    assert len(spans) == 1
    span = spans[0]
    assert span["kind"] == "agent" and span["name"] == "claude"
    assert span["status"] == "ok"
    assert span["trace_id"] == "t1"
    assert span["trace_schema_version"] == 2
    assert span["episode_id"] == tmp_path.name
    assert span["attempt_id"] == f"{tmp_path.name}:turn:1"
    assert "dur_ms" in span and span["dur_ms"] >= 0


def test_control_span_joins_episode_trace(tmp_path: Path) -> None:
    record_control_span(
        tmp_path,
        name="human_approval",
        status="approved",
        human_turn=3,
        data={"action_key": "now:1"},
    )
    span = _spans(tmp_path)[0]
    assert span["kind"] == "control"
    assert span["episode_id"] == tmp_path.name
    assert span["attempt_id"] == f"{tmp_path.name}:turn:3"
    assert span["data"] == {"action_key": "now:1"}


def test_tool_span_parented_to_agent(tmp_path: Path) -> None:
    rec = TraceRecorder(tmp_path, {}, None, human_turn=2)
    rec("agent_start", {"agent": "cursor", "round": 1})
    rec("tool_start", {"agent": "cursor", "round": 1, "tool": "sdk_edit"})
    rec("tool_output", {"agent": "cursor", "round": 1})
    rec("agent_done", {"agent": "cursor", "round": 1})
    spans = _spans(tmp_path)
    tool = next(s for s in spans if s["kind"] == "tool")
    agent = next(s for s in spans if s["kind"] == "agent")
    assert tool["name"] == "sdk_edit"
    assert tool["parent_id"] == agent["span_id"]


def test_cost_delta_attached_from_ledger(tmp_path: Path) -> None:
    run_meta: dict[str, Any] = {
        "cost_ledger": {"by_agent": {"claude": {"tokens_in": 100, "tokens_out": 10, "usd": 0.01}}}
    }
    rec = TraceRecorder(tmp_path, run_meta, None, human_turn=1)
    rec("agent_start", {"agent": "claude", "round": 1})
    # simulate record_agent_usage mutating the shared run_meta during the turn
    run_meta["cost_ledger"]["by_agent"]["claude"] = {"tokens_in": 1100, "tokens_out": 210, "usd": 0.05}
    rec("agent_done", {"agent": "claude", "round": 1})
    span = _spans(tmp_path)[0]
    assert span["tokens_in"] == 1000
    assert span["tokens_out"] == 200
    assert span["usd"] == pytest.approx(0.04)


def test_forwards_all_events_to_inner(tmp_path: Path) -> None:
    seen: list[tuple[str, dict[str, Any]]] = []
    rec = TraceRecorder(tmp_path, {}, lambda t, p: seen.append((t, p)), human_turn=1)
    for typ in ("agent_start", "agent_token", "agent_activity", "agent_done"):
        rec(typ, {"agent": "claude", "round": 1})
    assert [t for t, _ in seen] == ["agent_start", "agent_token", "agent_activity", "agent_done"]


def test_flush_marks_open_spans_incomplete(tmp_path: Path) -> None:
    rec = TraceRecorder(tmp_path, {}, None, human_turn=1)
    rec("agent_start", {"agent": "codex", "round": 1})
    rec("tool_start", {"agent": "codex", "round": 1, "tool": "codex_cli"})
    rec("turn_failed", {})
    spans = _spans(tmp_path)
    assert {s["kind"] for s in spans} == {"agent", "tool"}
    assert all(s["status"] == "incomplete" for s in spans)


def test_install_tracer_respects_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inner = lambda t, p: None  # noqa: E731
    monkeypatch.setenv("AGENT_LAB_TRACE", "0")
    assert install_tracer(tmp_path, {}, inner) is inner
    monkeypatch.setenv("AGENT_LAB_TRACE", "1")
    assert isinstance(install_tracer(tmp_path, {}, inner), TraceRecorder)


def test_run_room_writes_trace_jsonl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """End-to-end: a mock room turn flows through install_tracer → trace.jsonl."""
    from agent_mocks import patch_call_agent_reply

    from agent_lab import room

    monkeypatch.setenv("AGENT_LAB_TRACE", "1")
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)

    def fake_call_agent(agent: str, _system: str, user: str, **kwargs: Any) -> str:
        if kwargs.get("scribe"):
            return "## Plan\n\n- ok\n"
        return f"{agent} reply"

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, _messages, _plan = room.run_room(
        "Discuss a concrete plan.",
        agents=["cursor"],
        synthesize=True,
        parallel_rounds=1,
        sessions_base=tmp_path,
        turn_profile="analyze",
    )
    spans = _spans(folder)
    assert any(s["kind"] == "agent" and s["name"] == "cursor" for s in spans)


def test_trace_tail_and_snapshot(tmp_path: Path) -> None:
    rec = TraceRecorder(tmp_path, {}, None, human_turn=1)
    rec("agent_start", {"agent": "claude", "round": 1})
    rec("agent_done", {"agent": "claude", "round": 1})
    assert len(trace_tail(tmp_path)) == 1
    snap = observability_snapshot({}, folder=tmp_path)
    assert snap["trace_span_count"] == 1
    assert snap["trace_tail"][0]["kind"] == "agent"
    # no folder → empty, no crash
    assert observability_snapshot({})["trace_span_count"] == 0
