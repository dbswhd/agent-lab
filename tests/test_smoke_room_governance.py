"""Regression fixtures wired into smoke_room (governance + H-P4 context)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "smoke_room.py"


def _load_smoke_room():
    spec = importlib.util.spec_from_file_location("smoke_room", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_governance_fixtures_are_registered_and_valid():
    smoke = _load_smoke_room()

    assert "objection_blocks_execute" in smoke.SCENARIOS
    assert "challenge_revises_metric" in smoke.SCENARIOS

    for name in ("objection_blocks_execute", "challenge_revises_metric"):
        errors = smoke.validate_baseline(name, smoke.REGRESSION / name)
        assert errors == []


def test_governance_validators_reject_unlinked_shapes():
    smoke = _load_smoke_room()

    assert not smoke._check_objection_blocks_execute(
        {
            "objections": [
                {
                    "act": "BLOCK",
                    "status": "open",
                    "target_ref": "chat:1",
                }
            ]
        }
    )
    assert not smoke._check_challenge_revises_metric(
        {
            "objections": [
                {
                    "act": "CHALLENGE",
                    "status": "open",
                    "task_id": "t-1",
                }
            ],
            "tasks": [{"id": "t-1", "status": "pending"}],
        }
    )


def test_h_p4_fixtures_are_registered_and_valid():
    smoke = _load_smoke_room()

    for name in ("mailbox_handoff", "specialist_asymmetric_cwd"):
        assert name in smoke.SCENARIOS
        errors = smoke.validate_baseline(name, smoke.REGRESSION / name)
        assert errors == []


def test_h_p4_validators_reject_invalid_shapes():
    smoke = _load_smoke_room()

    assert not smoke._check_mailbox_handoff(
        {
            "mailbox": [{"from": "cursor", "to": "codex", "read": True}],
            "mailbox_unread": {"codex": 0},
        }
    )
    assert not smoke._check_specialist_asymmetric_cwd(
        {
            "turn_profile": "specialist",
            "agent_capabilities": {
                "cursor": {"cwd_role": "execute"},
                "codex": {"cwd_role": "execute"},
            },
            "turns": [{"mode": "discuss", "turn_profile": "specialist"}],
        }
    )
