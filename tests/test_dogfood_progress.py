"""Dogfood progress automation — status / record / auto (X1·X2 execute path)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "dogfood_progress.py"
_TOPICS = _ROOT / "sessions" / "_benchmark" / "topics" / "dogfood-v1.json"


def _load_progress():
    scripts = str(_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location("dogfood_progress", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_progress_splits_auto_and_manual(tmp_path: Path) -> None:
    prog = _load_progress()
    topics = prog._load_suite().load_topics(_TOPICS)
    log = [
        {"id": "S1", "session": "sessions/s1", "pass": True, "repeat": 1},
    ]
    out = prog.build_progress(topics, log)
    assert "S1" in out["done_ids"]
    assert "X2" in out["remaining_auto_ids"]  # scenario:x2_execute_oracle
    assert "X3" in out["remaining_auto_ids"]  # scenario:x3_verify_repair
    assert "L4" in out["remaining_manual_ids"]  # still skip:/live
    assert out["done"] >= 1
    assert out["pct_done"] > 0


def test_append_suite_log_roundtrip(tmp_path: Path) -> None:
    prog = _load_progress()
    log_path = tmp_path / "suite-log.json"
    row = prog.append_suite_log(
        log_path,
        topic_id="S2",
        session="sessions/demo",
        passed=True,
        notes="unit",
    )
    assert row["id"] == "S2"
    assert row["pass"] is True
    loaded = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(loaded) == 1
    assert loaded[0]["session"] == "sessions/demo"


def test_append_suite_log_judge_defaults_to_none(tmp_path: Path) -> None:
    prog = _load_progress()
    log_path = tmp_path / "suite-log.json"
    row = prog.append_suite_log(
        log_path,
        topic_id="S3",
        session="sessions/demo",
        passed=True,
    )
    assert row["judge"] is None


def test_append_suite_log_carries_judge_summary(tmp_path: Path) -> None:
    prog = _load_progress()
    log_path = tmp_path / "suite-log.json"
    judge = {"enabled": True, "source": "live", "overall": 4.0, "verdict": "pass", "usd_per_point": 0.05}
    row = prog.append_suite_log(
        log_path,
        topic_id="S4",
        session="sessions/demo",
        passed=True,
        judge=judge,
    )
    assert row["judge"] == judge


def test_judge_summary_disabled_without_judge_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--judge-live without AGENT_LAB_JUDGE_LIVE=1 must not crash — judge_session()
    itself gates the live call, so this only ever reduces its output."""
    monkeypatch.delenv("AGENT_LAB_JUDGE_LIVE", raising=False)
    prog = _load_progress()
    folder = tmp_path / "sess-demo"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    (folder / "chat.jsonl").write_text("", encoding="utf-8")
    summary = prog._judge_summary(str(folder))
    assert summary.get("enabled") is not True


def test_x1_x2_catalog_are_scenario_automatable() -> None:
    prog = _load_progress()
    suite = prog._load_suite()
    rows = {r["id"]: r for r in suite.load_topics(_TOPICS)}
    assert rows["X1"]["mock"] == "scenario:mission_dogfood"
    assert rows["X2"]["mock"] == "scenario:x2_execute_oracle"
    assert rows["X1"]["live_only"] is False
    assert rows["X2"]["live_only"] is False
    ok1, reason1 = prog._topic_automatable(rows["X1"])
    ok2, reason2 = prog._topic_automatable(rows["X2"])
    assert ok1 and "mission" in reason1
    assert ok2 and "x2" in reason2


def test_auto_dry_run_lists_x2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    prog = _load_progress()
    suite = prog._load_suite()
    topics = suite.filter_topics(suite.load_topics(_TOPICS), {"X"}, {"X2"})
    log_path = tmp_path / "suite-log.json"
    log_path.write_text("[]\n", encoding="utf-8")
    rc = prog.run_auto(
        topics,
        log_path=log_path,
        sessions_base=tmp_path / "sessions",
        only={"X2"},
        skip_done=True,
        dry_run=True,
    )
    assert rc == 0
    # dry-run must not append
    assert json.loads(log_path.read_text(encoding="utf-8")) == []


def test_scenario_x2_execute_oracle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """X2 suite scenario: plan → approve → dry-run → Oracle pass."""
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "0")
    monkeypatch.setenv("AGENT_LAB_ORACLE_LIVE", "0")
    # Isolate outcomes ledger so we don't pollute the repo ledger.
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "outcomes-root"))
    suite = _load_progress()._load_suite()
    rows = suite.load_topics(_TOPICS)
    entry = next(r for r in rows if r["id"] == "X2")
    out = suite.scenario_x2_execute_oracle(entry, tmp_path / "sessions")
    assert out["ok"] is True
    assert out.get("session_id")
    assert "oracle=pass" in str(out.get("detail") or "")


def test_scenario_mission_dogfood_x1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_LOOP", "1")
    suite = _load_progress()._load_suite()
    rows = suite.load_topics(_TOPICS)
    entry = next(r for r in rows if r["id"] == "X1")
    out = suite.scenario_mission_dogfood(entry, tmp_path / "sessions")
    assert out["ok"] is True
    assert "MISSION_DONE" in str(out.get("detail") or "")
