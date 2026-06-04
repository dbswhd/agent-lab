"""LC-L3 execute verify loop regression fixture skeleton."""

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


def test_execute_verify_loop_fixture_registered_and_valid():
    smoke = _load_smoke_room()

    assert "execute_verify_loop" in smoke.SCENARIOS
    errors = smoke.validate_baseline(
        "execute_verify_loop",
        smoke.REGRESSION / "execute_verify_loop",
    )
    assert errors == []


def test_execute_verify_loop_validator_requires_passed_oracle_after_retry():
    smoke = _load_smoke_room()

    valid = {
        "executions": [
            {
                "status": "merged",
                "verify_retries": 1,
                "reverify_endpoint": "/api/sessions/{session_id}/execute/reverify",
                "verify_after_merge": {
                    "status": "passed",
                    "source": "mock_oracle",
                    "oracle": {
                        "verdict": "pass",
                        "checked_paths": ["src/app.py"],
                    },
                },
                "verify_history": [
                    {"attempt": 0, "status": "failed"},
                    {"attempt": 1, "status": "passed"},
                ],
            }
        ]
    }
    assert smoke._check_execute_verify_loop(valid)

    no_retry = {
        "executions": [
            {
                "status": "merged",
                "verify_retries": 0,
                "reverify_endpoint": "/api/sessions/{session_id}/execute/reverify",
                "verify_after_merge": {
                    "status": "passed",
                    "source": "mock_oracle",
                    "oracle": {
                        "verdict": "pass",
                        "checked_paths": ["src/app.py"],
                    },
                },
                "verify_history": [
                    {"attempt": 0, "status": "passed"},
                    {"attempt": 1, "status": "passed"},
                ],
            }
        ]
    }
    assert not smoke._check_execute_verify_loop(no_retry)

    failed = {
        "executions": [
            {
                "status": "merged",
                "verify_retries": 1,
                "reverify_endpoint": "/api/sessions/{session_id}/execute/reverify",
                "verify_after_merge": {
                    "status": "failed",
                    "source": "mock_oracle",
                    "oracle": {
                        "verdict": "fail",
                        "checked_paths": ["src/app.py"],
                    },
                },
                "verify_history": [
                    {"attempt": 0, "status": "failed"},
                    {"attempt": 1, "status": "failed"},
                ],
            }
        ]
    }
    assert not smoke._check_execute_verify_loop(failed)
