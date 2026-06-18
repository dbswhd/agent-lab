"""G004 — optional goal_ledger in run.json (schema-valid, crash-recovery compatible)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab import goal_ledger
from agent_lab.run_schema import RuntimeValidationError, validate_run


def _write(folder: Path, run: dict) -> None:
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")


def test_append_goal_event_persists(tmp_path: Path) -> None:
    from agent_lab.run_meta import read_run_meta

    _write(tmp_path, {"mission_loop": {"phase": "DISCUSS"}})
    goal_ledger.append_goal_event(tmp_path, "mode_route", mode="CONSENSUS", phase="DISCUSS")
    led = read_run_meta(tmp_path).get("goal_ledger", [])
    assert len(led) == 1
    assert led[0]["event"] == "mode_route" and led[0]["mode"] == "CONSENSUS" and led[0]["at"]


def test_append_goal_event_dedup(tmp_path: Path) -> None:
    from agent_lab.run_meta import read_run_meta

    _write(tmp_path, {})
    goal_ledger.append_goal_event(tmp_path, "mode_route", mode="CLARIFY", dedup_mode=True)
    goal_ledger.append_goal_event(tmp_path, "mode_route", mode="CLARIFY", dedup_mode=True)
    goal_ledger.append_goal_event(tmp_path, "mode_route", mode="CONSENSUS", dedup_mode=True)
    led = read_run_meta(tmp_path).get("goal_ledger", [])
    assert [e["mode"] for e in led] == ["CLARIFY", "CONSENSUS"]


def test_append_goal_event_capped(tmp_path: Path) -> None:
    from agent_lab.run_meta import read_run_meta

    _write(tmp_path, {})
    for i in range(goal_ledger.GOAL_LEDGER_CAP + 25):
        goal_ledger.append_goal_event(tmp_path, "tick", note=str(i))
    led = read_run_meta(tmp_path).get("goal_ledger", [])
    assert len(led) == goal_ledger.GOAL_LEDGER_CAP
    assert led[-1]["note"] == str(goal_ledger.GOAL_LEDGER_CAP + 24)


def test_validate_run_goal_ledger() -> None:
    validate_run({"goal_ledger": [{"event": "x"}]})  # ok
    validate_run({"goal_ledger": []})  # ok
    with pytest.raises(RuntimeValidationError):
        validate_run({"goal_ledger": "nope"})
    with pytest.raises(RuntimeValidationError):
        validate_run({"goal_ledger": ["nope"]})


def test_crash_recovery_roundtrip_compat(tmp_path: Path) -> None:
    from agent_lab.run_meta import patch_run_meta, read_run_meta

    _write(tmp_path, {"mission_loop": {"phase": "VERIFY"}, "goal_ledger": [{"event": "mode_route", "mode": "EXECUTE"}]})
    run = read_run_meta(tmp_path)  # validates on read
    assert run["goal_ledger"][0]["mode"] == "EXECUTE"
    patch_run_meta(tmp_path, lambda r: r)  # validates on patch (crash_recovery path)
    assert read_run_meta(tmp_path)["goal_ledger"][0]["mode"] == "EXECUTE"


def test_maybe_advance_appends_ledger_when_flag_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_PIPELINE", "1")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    _write(tmp_path, {
        "mission_loop": {"enabled": True, "phase": "CLARIFY", "autonomous_segment": {"active": True}},
        "verified_loop": {"loop_goal": {"text": "make it better"}},
    })
    maybe_advance_mission(tmp_path, scheduled=True)
    led = read_run_meta(tmp_path).get("goal_ledger", [])
    assert any(e.get("event") == "mode_route" and e.get("mode") == "CLARIFY" for e in led)


def test_maybe_advance_no_ledger_when_flag_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_PIPELINE", raising=False)
    from agent_lab.mission_advance import maybe_advance_mission
    from agent_lab.run_meta import read_run_meta

    _write(tmp_path, {"mission_loop": {"enabled": True, "phase": "DISCUSS", "autonomous_segment": {"active": True}}})
    maybe_advance_mission(tmp_path, scheduled=True)
    assert "goal_ledger" not in read_run_meta(tmp_path)
