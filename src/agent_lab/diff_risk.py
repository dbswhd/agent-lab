"""Diff risk classification for Trust-gated Auto-approval.

Classifies a pending execution as low / medium / high risk based on
diff characteristics, file patterns, and safety scan results.
"""

from __future__ import annotations

import re
from typing import Any, Literal

RiskLevel = Literal["low", "medium", "high"]

# Paths matching any of these patterns are considered sensitive (→ medium min)
_SENSITIVE_PATTERNS: list[str] = [
    r"auth",
    r"secret",
    r"cred",
    r"password",
    r"api[_-]?key",
    r"migrations?/",
    r"\.env",
    r"ci\.ya?ml",
    r"github/workflows",
    r"permission",
    r"pyproject\.toml",
    r"package\.json",
    r"setup\.(py|cfg)$",
    r"dockerfile",
    r"docker.?compose",
]

# Paths matching any of these are low-risk content (docs/tests/fixtures)
_SAFE_PATTERNS: list[str] = [
    r"^docs?/",
    r"^documentation/",
    r"^tests?/",
    r"(^|/)test_",
    r"_test\.py$",
    r"\.md$",
    r"\.txt$",
    r"\.rst$",
    r"(^|/)changelog",
    r"(^|/)readme",
    r"fixtures/",
]

_LOW_DIFF_LINES = 50
_MEDIUM_DIFF_LINES = 300


def _count_changed_lines(diff: str | None) -> int:
    count = 0
    for line in (diff or "").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            count += 1
        elif line.startswith("-") and not line.startswith("---"):
            count += 1
    return count


def _matches_any(path: str, patterns: list[str]) -> bool:
    p = path.lower().replace("\\", "/")
    return any(re.search(pat, p) for pat in patterns)


def assess_diff_risk(execution: dict[str, Any]) -> tuple[RiskLevel, list[str]]:
    """Return (risk_level, reasons) for a pending execution.

    Inputs are read from the execution dict (as stored in run.json):
    - safety_scan: from diff_safety.scan_diff()
    - paths_outside_expected, needs_artifact_review
    - touched_paths or source_touched_paths
    - diff (unified diff text)
    """
    reasons: list[str] = []

    # Blocking safety scan finding → always high
    scan = execution.get("safety_scan") or {}
    if isinstance(scan, dict) and not scan.get("ok", True):
        reasons.append("safety_scan_block")
        return "high", reasons

    # Agent wrote outside expected scope → medium
    if execution.get("paths_outside_expected"):
        reasons.append("paths_outside_expected")

    # Non-code artifact changes require human eyes
    if execution.get("needs_artifact_review"):
        reasons.append("needs_artifact_review")

    if reasons:
        return "medium", reasons

    touched = list(execution.get("touched_paths") or execution.get("source_touched_paths") or [])

    # Sensitive path patterns → medium
    sensitive = [p for p in touched if _matches_any(p, _SENSITIVE_PATTERNS)]
    if sensitive:
        reasons.append(f"sensitive_paths:{','.join(sensitive[:3])}")
        return "medium", reasons

    diff_lines = _count_changed_lines(str(execution.get("diff") or ""))

    if diff_lines > _MEDIUM_DIFF_LINES:
        reasons.append(f"large_diff:{diff_lines}_lines")
        return "high", reasons

    if diff_lines > _LOW_DIFF_LINES:
        reasons.append(f"medium_diff:{diff_lines}_lines")
        return "medium", reasons

    # Low risk: small or safe-only diff
    if touched and all(_matches_any(p, _SAFE_PATTERNS) for p in touched):
        reasons.append("safe_paths_only")
    elif not touched:
        reasons.append("no_files_changed")
    else:
        reasons.append(f"small_diff:{diff_lines}_lines")
    return "low", reasons
