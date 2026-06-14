"""Dogfood eval suite runner — mock scenarios + checklist + aggregate."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "run_dogfood_suite.py"
_TOPICS = _ROOT / "sessions" / "_benchmark" / "topics" / "dogfood-v1.json"
_EXAMPLE_LOG = _ROOT / "sessions" / "_benchmark" / "topics" / "suite-log.example.json"


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_dogfood_suite", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dogfood_v1_catalog_shape():
    rows = json.loads(_TOPICS.read_text(encoding="utf-8"))
    assert len(rows) >= 29
    ids = {str(r["id"]) for r in rows}
    assert {"S1", "M4", "L1", "X1", "A2", "D1", "PW1", "PW2"}.issubset(ids)
    for row in rows:
        assert row.get("topic")
        assert row.get("tier")
        assert row.get("category")


def test_checklist_mode_exits_zero(capsys):
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--mode", "checklist", "--tier", "S", "--only", "S1"],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "S1" in proc.stdout
    assert "pass 기준" in proc.stdout or "pass" in proc.stdout.lower()


def test_mock_scenario_m4_challenge_amend(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "0")
    runner = _load_runner()
    rows = runner.load_topics(_TOPICS)
    entry = next(r for r in rows if r["id"] == "M4")
    out = runner.scenario_challenge_amend(entry, tmp_path)
    assert out["ok"] is True


def test_mock_scenario_m5_dispatch_parallel(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "0")
    runner = _load_runner()
    rows = runner.load_topics(_TOPICS)
    entry = next(r for r in rows if r["id"] == "M5")
    out = runner.scenario_dispatch_parallel(entry, tmp_path)
    assert out["ok"] is True


@pytest.mark.parametrize(
    "topic_id,scenario_fn",
    [
        ("PW2", "scenario_plan_fsm_human_pending"),
        ("PW3", "scenario_plan_clarify_cap"),
        ("PW4", "scenario_plan_peer_cap"),
        ("PW5", "scenario_plan_approve_latency"),
    ],
)
def test_mock_plan_workflow_scenarios(
    tmp_path, monkeypatch, topic_id: str, scenario_fn: str
):
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "0")
    runner = _load_runner()
    rows = runner.load_topics(_TOPICS)
    entry = next(r for r in rows if r["id"] == topic_id)
    fn = getattr(runner, scenario_fn)
    out = fn(entry, tmp_path)
    assert out["ok"] is True


def test_aggregate_example_log(tmp_path):
    runner = _load_runner()
    rows = runner.load_topics(_TOPICS)
    # Example sessions do not exist — aggregate should warn but exit 0
    rc = runner.run_aggregate(rows, _EXAMPLE_LOG)
    assert rc == 0
