"""Tests for diff risk classification."""

from __future__ import annotations


from agent_lab.diff_risk import (
    _count_changed_lines,
    _matches_any,
    assess_diff_risk,
)


def _exec(
    *,
    diff: str = "",
    touched_paths: list[str] | None = None,
    safety_ok: bool = True,
    safety_blocking: bool = False,
    paths_outside: bool = False,
    needs_artifact: bool = False,
) -> dict:
    ex: dict = {
        "status": "pending_approval",
        "diff": diff,
        "touched_paths": touched_paths or [],
        "paths_outside_expected": paths_outside,
        "needs_artifact_review": needs_artifact,
    }
    if not safety_ok or safety_blocking:
        ex["safety_scan"] = {
            "ok": False,
            "findings": [{"severity": "block"}],
            "counts": {"blocking": 1},
        }
    else:
        ex["safety_scan"] = {"ok": True, "findings": [], "counts": {"blocking": 0}}
    return ex


def test_count_changed_lines_basic() -> None:
    diff = "+added line\n-removed line\n context\n+++ b/file.py"
    assert _count_changed_lines(diff) == 2


def test_count_changed_lines_ignores_headers() -> None:
    diff = "+++ b/file.py\n--- a/file.py\n+actual addition"
    assert _count_changed_lines(diff) == 1


def test_safety_scan_block_is_always_high() -> None:
    level, reasons = assess_diff_risk(_exec(safety_ok=False))
    assert level == "high"
    assert "safety_scan_block" in reasons


def test_paths_outside_expected_is_medium() -> None:
    level, reasons = assess_diff_risk(_exec(paths_outside=True))
    assert level == "medium"
    assert "paths_outside_expected" in reasons


def test_needs_artifact_review_is_medium() -> None:
    level, reasons = assess_diff_risk(_exec(needs_artifact=True))
    assert level == "medium"
    assert "needs_artifact_review" in reasons


def test_sensitive_path_auth_is_medium() -> None:
    level, reasons = assess_diff_risk(_exec(touched_paths=["src/auth/middleware.py"]))
    assert level == "medium"
    assert any("sensitive" in r for r in reasons)


def test_sensitive_path_env_is_medium() -> None:
    level, reasons = assess_diff_risk(_exec(touched_paths=[".env.production"]))
    assert level == "medium"


def test_sensitive_path_migrations_is_medium() -> None:
    level, reasons = assess_diff_risk(_exec(touched_paths=["db/migrations/0042_add_column.sql"]))
    assert level == "medium"


def test_large_diff_is_high() -> None:
    # Generate a diff with > 300 lines
    diff = "\n".join(f"+line {i}" for i in range(350))
    level, reasons = assess_diff_risk(_exec(diff=diff))
    assert level == "high"
    assert any("large_diff" in r for r in reasons)


def test_medium_diff_is_medium() -> None:
    diff = "\n".join(f"+line {i}" for i in range(100))
    level, reasons = assess_diff_risk(_exec(diff=diff))
    assert level == "medium"
    assert any("medium_diff" in r for r in reasons)


def test_small_diff_is_low() -> None:
    diff = "\n".join(f"+line {i}" for i in range(20))
    level, reasons = assess_diff_risk(_exec(diff=diff, touched_paths=["src/utils.py"]))
    assert level == "low"
    assert any("small_diff" in r for r in reasons)


def test_docs_only_is_low() -> None:
    level, reasons = assess_diff_risk(
        _exec(
            diff="+minor edit",
            touched_paths=["docs/guide.md", "README.md"],
        )
    )
    assert level == "low"
    assert "safe_paths_only" in reasons


def test_tests_only_is_low() -> None:
    level, reasons = assess_diff_risk(
        _exec(
            diff="+assert foo == bar",
            touched_paths=["tests/test_utils.py"],
        )
    )
    assert level == "low"


def test_no_files_changed_is_low() -> None:
    level, reasons = assess_diff_risk(_exec())
    assert level == "low"
    assert "no_files_changed" in reasons


def test_matches_any_case_insensitive() -> None:
    assert _matches_any("src/Auth/login.py", ["auth"])
    assert _matches_any("Config.ENV", [r"\.env"])
    assert not _matches_any("utils/helper.py", ["auth", "secret"])
