"""Unified dogfood track — gate evaluation + X3/X4 suite scenarios."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "dogfood_track.py"
_TOPICS = _ROOT / "sessions" / "_benchmark" / "topics" / "dogfood-v1.json"


def _load_track():
    scripts = str(_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location("dogfood_track", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_suite():
    scripts = str(_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    path = _ROOT / "scripts" / "run_dogfood_suite.py"
    spec = importlib.util.spec_from_file_location("run_dogfood_suite", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_evaluate_gates_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    track = _load_track()
    monkeypatch.setattr(track, "STATE_PATH", tmp_path / "dogfood-track.json")
    monkeypatch.setattr(track, "DEFAULT_LOG", tmp_path / "suite-log.json")
    (tmp_path / "suite-log.json").write_text("[]\n", encoding="utf-8")
    report = track.evaluate_gates(outcomes_root=tmp_path)
    ids = [g["id"] for g in report["gates"]]
    assert ids == ["P0-5", "F7", "N4-D3", "CATALOG", "HS-M5", "N1-30"]
    assert report["total"] == 6
    assert report["met"] <= 6
    # Empty ledger → live closes unmet
    assert report["all_met"] is False
    p05 = next(g for g in report["gates"] if g["id"] == "P0-5")
    assert p05["met"] is False
    assert "history.n≥3" in p05["metrics"]["need"]


def test_record_f7_decision_and_hs_m5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    track = _load_track()
    monkeypatch.setattr(track, "STATE_PATH", tmp_path / "dogfood-track.json")
    assert track.record_f7_decision("ON", rationale="unit") == 0
    state = track._load_state()
    assert state["f7"]["decision"] == "ON"
    assert track.record_hs_m5_merge(candidate_id="c1") == 0
    state = track._load_state()
    assert state["hs_m5"]["merged_at"]
    assert state["hs_m5"]["candidate_id"] == "c1"


def test_x3_x4_catalog_scenarios() -> None:
    suite = _load_suite()
    rows = {r["id"]: r for r in suite.load_topics(_TOPICS)}
    assert rows["X3"]["mock"] == "scenario:x3_verify_repair"
    assert rows["X4"]["mock"] == "scenario:x4_pre_execute_hook"
    assert rows["X3"]["live_only"] is False
    assert rows["X4"]["live_only"] is False


def test_scenario_x3_verify_repair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_LOOP", "1")
    suite = _load_suite()
    entry = next(r for r in suite.load_topics(_TOPICS) if r["id"] == "X3")
    out = suite.scenario_x3_verify_repair(entry, tmp_path / "sessions")
    assert out["ok"] is True
    assert "MISSION_DONE" in str(out.get("detail") or "") or "repairs=1" in str(out.get("detail") or "")


def test_scenario_x4_pre_execute_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    suite = _load_suite()
    entry = next(r for r in suite.load_topics(_TOPICS) if r["id"] == "X4")
    out = suite.scenario_x4_pre_execute_hook(entry, tmp_path / "sessions")
    assert out["ok"] is True
    assert "hook_blocks=" in str(out.get("detail") or "")


def test_render_status_live_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    track = _load_track()
    monkeypatch.setattr(track, "STATE_PATH", tmp_path / "dogfood-track.json")
    monkeypatch.setattr(track, "DEFAULT_LOG", tmp_path / "suite-log.json")
    (tmp_path / "suite-log.json").write_text("[]\n", encoding="utf-8")
    text = track.render_status(track.evaluate_gates(outcomes_root=tmp_path))
    assert "live-first" in text
    assert "P0-5" in text
    assert "dogfood-track-env" in text or "make dogfood-track" in text
    assert "mock:" not in text


def test_run_live_bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    track = _load_track()
    monkeypatch.setattr(track, "STATE_PATH", tmp_path / "dogfood-track.json")
    monkeypatch.setattr(track, "DEFAULT_LOG", tmp_path / "suite-log.json")
    monkeypatch.setattr(track, "REPORTS", tmp_path / "reports")
    (tmp_path / "suite-log.json").write_text("[]\n", encoding="utf-8")
    rc = track.run_live(skip_f7_start=False)
    assert rc == 0
    state = track._load_state()
    assert state["f7"].get("start_date")
    out = capsys.readouterr().out
    assert "LIVE env" in out
    assert "AGENT_LAB_MOCK_AGENTS" in out
    assert "unset AGENT_LAB_MOCK_AGENTS" in out
