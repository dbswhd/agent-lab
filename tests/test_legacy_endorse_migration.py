"""HOOK-COMM P3: LEGACY_ENDORSE=0 default + envelope regression fixtures."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from agent_lab.agent_envelope import classify_consensus_reply
from agent_lab.reply_policy import legacy_endorse_enabled
from agent_lab.session_score import score_session

ROOT = Path(__file__).resolve().parents[1]
REGRESSION = ROOT / "sessions" / "_regression"
_SCRIPT = ROOT / "scripts" / "smoke_room.py"
_DOGFOOD_SCRIPT = ROOT / "scripts" / "mission_dogfood_report.py"


def _load_smoke_room():
    spec = importlib.util.spec_from_file_location("smoke_room", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_legacy_endorse_default_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_LEGACY_ENDORSE", raising=False)
    assert legacy_endorse_enabled() is False
    assert classify_consensus_reply("이의 없습니다") == "neutral"


def test_envelope_consensus_regression_fixture() -> None:
    smoke = _load_smoke_room()
    errors = smoke.validate_baseline(
        "envelope_consensus_endorse",
        REGRESSION / "envelope_consensus_endorse",
    )
    assert errors == []


def test_mission_dogfood_regression_fixture_scores() -> None:
    folder = REGRESSION / "mission_loop_dogfood_ok"
    report = score_session(folder)
    ml = report["counts"]["mission_loop"]
    assert ml["enabled"] == 1
    assert ml["phase_terminal_done"] == 1
    assert ml["notepad_chars"] >= 200
    assert report["scores"]["mission_completed"] == 1.0


def test_mission_dogfood_report_script_ok() -> None:
    spec = importlib.util.spec_from_file_location(
        "mission_dogfood_report",
        _DOGFOOD_SCRIPT,
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    payload = mod.evaluate(REGRESSION / "mission_loop_dogfood_ok")
    assert payload["ok"] is True


def test_regression_communicate_meta_no_legacy_endorse() -> None:
    """All regression turns should record zero legacy endorse when default off."""
    for folder in REGRESSION.iterdir():
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        run_path = folder / "run.json"
        if not run_path.is_file():
            continue
        run = json.loads(run_path.read_text(encoding="utf-8"))
        for turn in run.get("turns") or []:
            if not isinstance(turn, dict):
                continue
            meta = turn.get("communicate_meta") or {}
            if not isinstance(meta, dict):
                continue
            assert int(meta.get("legacy_endorse_count") or 0) == 0, folder.name
