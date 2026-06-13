"""Tests for Trading Mission telemetry (P2 #19)."""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.trading_mission.telemetry import (
    aggregate_turn_telemetry,
    append_token_log_line,
    build_mission_telemetry,
    parse_discuss_rounds_from_plan,
    record_mission_telemetry,
)


def test_parse_discuss_rounds_from_plan():
    plan = "## 합의\n- discuss_rounds_used: 2\n"
    assert parse_discuss_rounds_from_plan(plan) == 2
    assert parse_discuss_rounds_from_plan("no rounds") is None


def test_aggregate_turn_telemetry_sums_context():
    run = {
        "turns": [
            {
                "agent_parallel_rounds": 1,
                "latency_ms": 1200,
                "agents": ["cursor", "codex", "claude"],
                "context": {
                    "payload_chars_total": 4000,
                    "summary": {"payload_chars_max": 2000},
                },
            },
            {
                "agent_parallel_rounds": 2,
                "latency_ms": 800,
                "agents": ["cursor"],
                "context": {
                    "payload_chars_total": 1000,
                    "summary": {"payload_chars_max": 1000},
                },
            },
        ]
    }
    stats = aggregate_turn_telemetry(run)
    assert stats["human_turns"] == 2
    assert stats["agent_parallel_rounds_max"] == 2
    assert stats["agent_invocations"] == 4
    assert stats["latency_ms_total"] == 2000
    assert stats["payload_chars_total"] == 5000
    assert stats["payload_chars_max"] == 2000


def test_build_mission_telemetry_uses_plan_rounds(tmp_path: Path):
    session = tmp_path / "sess-tel"
    session.mkdir()
    (session / "plan.md").write_text(
        "# plan\n\n## 합의\n- discuss_rounds_used: 1\n",
        encoding="utf-8",
    )
    (session / "run.json").write_text(
        json.dumps(
            {
                "turns": [
                    {
                        "agent_parallel_rounds": 1,
                        "latency_ms": 500,
                        "agents": ["cursor", "codex", "claude"],
                        "context": {"payload_chars_total": 8000, "summary": {}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    tel = build_mission_telemetry(
        session,
        mission_kind="trading_premarket",
        wall_ms=12.5,
    )

    assert tel["mission_kind"] == "trading_premarket"
    assert tel["discuss_rounds_used"] == 1
    assert tel["tokens_estimated"]["input"] == 2000
    assert tel["wall_ms"] == 12.5
    assert tel["agent_invocations"] == 3


def test_record_mission_telemetry_patches_run_json(tmp_path: Path, monkeypatch):
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    (pipeline / "tasks").mkdir()
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))

    session = tmp_path / "sess-record"
    session.mkdir()
    (session / "plan.md").write_text(
        "# plan\n\n## 합의\n- discuss_rounds_used: 0\n",
        encoding="utf-8",
    )
    (session / "run.json").write_text("{}", encoding="utf-8")

    record_mission_telemetry(
        session,
        mission_kind="trading_blocked",
        discuss_skipped=True,
    )

    run = json.loads((session / "run.json").read_text(encoding="utf-8"))
    assert run["mission_telemetry"]["mission_kind"] == "trading_blocked"
    assert run["mission_telemetry"]["discuss_skipped"] is True
    assert len(run["mission_telemetry_history"]) == 1

    log_path = pipeline / "tasks" / ".token_log.jsonl"
    assert log_path.is_file()
    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert line["task"] == "trading_mission:trading_blocked"
    assert line["discuss_rounds"] == 0


def test_append_token_log_skips_without_pipeline_root(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("QUANT_PIPELINE_ROOT", raising=False)
    assert append_token_log_line({"recorded_at": "t", "mission_kind": "x"}) is None
