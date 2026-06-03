"""Layer 4 adversarial_gate_lgtm fixture skeleton (mock-only, no live LLM)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from agent_lab.adversarial_gate import LGTM_TOKEN, badge_tone, mock_adversarial_note

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "sessions" / "_regression" / "adversarial_gate_lgtm"
_SCRIPT = ROOT / "scripts" / "smoke_room.py"


def _load_smoke_room():
    spec = importlib.util.spec_from_file_location("smoke_room", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mock_adversarial_note_lgtm_and_warning():
    assert mock_adversarial_note(action_what="fixture", diff="") == LGTM_TOKEN
    assert mock_adversarial_note(action_what="fixture", diff="+ clean change") == LGTM_TOKEN
    warning = mock_adversarial_note(action_what="fixture", diff="+ # TODO: fix later")
    assert warning != LGTM_TOKEN
    assert badge_tone(LGTM_TOKEN) == "lgtm"
    assert badge_tone(warning) == "warning"


def test_adversarial_gate_fixture_registered_and_valid():
    smoke = _load_smoke_room()

    assert "adversarial_gate_lgtm" in smoke.SCENARIOS
    errors = smoke.validate_baseline("adversarial_gate_lgtm", FIXTURE)
    assert errors == []


def test_adversarial_gate_validator_rejects_missing_note():
    smoke = _load_smoke_room()

    assert not smoke._check_adversarial_gate_lgtm(
        {
            "executions": [
                {
                    "status": "review_required",
                    "adversarial_source": "mock",
                }
            ]
        }
    )


def test_run_fixture_has_mock_adversarial_note():
    run = json.loads((FIXTURE / "run.json").read_text(encoding="utf-8"))
    rows = run["executions"]

    assert any(
        row.get("status") == "review_required"
        and row.get("adversarial_note") == LGTM_TOKEN
        and row.get("adversarial_source") == "mock"
        for row in rows
    )
