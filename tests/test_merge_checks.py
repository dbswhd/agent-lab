"""Integration: diff safety scan gates merge via build_merge_checks (G6)."""

from __future__ import annotations

from typing import Any

from agent_lab.merge_checks import build_merge_checks


def _execution(safety_scan: dict[str, Any] | None) -> dict[str, Any]:
    execution: dict[str, Any] = {
        "id": "e1",
        "status": "pending_approval",
        "isolation_effective": "apply",
    }
    if safety_scan is not None:
        execution["safety_scan"] = safety_scan
    return {"executions": [execution]}


def _diff_safety_check(checks: list[dict[str, Any]]) -> dict[str, Any]:
    return next(c for c in checks if c["id"] == "diff_safety")


def test_blocking_finding_disables_merge() -> None:
    scan = {
        "ok": False,
        "findings": [{"kind": "secret", "rule": "aws_access_key", "file": "a.py", "line": 1, "severity": "block"}],
        "counts": {"secret": 1, "danger": 0, "blocking": 1},
    }
    result = build_merge_checks(_execution(scan))
    assert result["merge_disabled"] is True
    assert _diff_safety_check(result["checks"])["ok"] is False


def test_clean_scan_does_not_block_on_safety() -> None:
    scan = {"ok": True, "findings": [], "counts": {"secret": 0, "danger": 0, "blocking": 0}}
    check = _diff_safety_check(build_merge_checks(_execution(scan))["checks"])
    assert check["ok"] is True
    assert check["detail"] == "clean"


def test_warn_only_finding_does_not_block() -> None:
    scan = {
        "ok": True,
        "findings": [{"kind": "secret", "rule": "aws_access_key", "file": "tests/x.py", "line": 1, "severity": "warn"}],
        "counts": {"secret": 1, "danger": 0, "blocking": 0},
    }
    check = _diff_safety_check(build_merge_checks(_execution(scan))["checks"])
    assert check["ok"] is True


def test_unscanned_execution_is_ok() -> None:
    check = _diff_safety_check(build_merge_checks(_execution(None))["checks"])
    assert check["ok"] is True
    assert check["detail"] == "not scanned"
