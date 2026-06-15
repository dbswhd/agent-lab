"""Verify failure classification and repair policy."""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any


class FailureCode(str, Enum):
    MERGE_CONFLICT = "merge_conflict"
    ORACLE_FAIL = "oracle_fail"
    ORACLE_SKIP = "oracle_skip"
    WORKTREE_GIT_DIRTY = "worktree_git_dirty"
    EXECUTE_AGENT_ERROR = "execute_agent_error"
    TIMEOUT = "timeout"
    ISOLATION_BLOCKED = "isolation_blocked"
    STRUCTURAL = "structural"
    UNKNOWN = "unknown"


_POLICY: dict[FailureCode, dict[str, Any]] = {
    FailureCode.MERGE_CONFLICT: {
        "label": "merge_conflict",
        "recoverable": True,
        "max_repair": 3,
        "repair": "merge_repair",
        "circuit_breaker_after": 3,
        "fallback": "discuss",
    },
    FailureCode.ORACLE_FAIL: {
        "label": "oracle_fail",
        "recoverable": True,
        "max_repair": 2,
        "repair": "reverify",
        "circuit_breaker_after": 2,
        "fallback": "discuss",
    },
    FailureCode.ORACLE_SKIP: {
        "label": "oracle_skip",
        "recoverable": True,
        "max_repair": 0,
        "repair": "none",
        "circuit_breaker_after": 0,
        "fallback": "discuss",
    },
    FailureCode.WORKTREE_GIT_DIRTY: {
        "label": "worktree_git_dirty",
        "recoverable": True,
        "max_repair": 2,
        "repair": "worktree_recreate",
        "circuit_breaker_after": 2,
        "fallback": "discuss",
    },
    FailureCode.EXECUTE_AGENT_ERROR: {
        "label": "execute_agent_error",
        "recoverable": True,
        "max_repair": 2,
        "repair": "reinvoke",
        "circuit_breaker_after": 2,
        "fallback": "discuss",
    },
    FailureCode.TIMEOUT: {
        "label": "timeout",
        "recoverable": True,
        "max_repair": 2,
        "repair": "reinvoke",
        "circuit_breaker_after": 2,
        "fallback": "discuss",
    },
    FailureCode.ISOLATION_BLOCKED: {
        "label": "isolation_blocked",
        "recoverable": False,
        "max_repair": 0,
        "repair": "none",
        "circuit_breaker_after": 0,
        "fallback": "discuss",
    },
    FailureCode.STRUCTURAL: {
        "label": "structural",
        "recoverable": False,
        "max_repair": 0,
        "repair": "none",
        "circuit_breaker_after": 0,
        "fallback": "circuit_breaker",
    },
    FailureCode.UNKNOWN: {
        "label": "unknown",
        "recoverable": True,
        "max_repair": 1,
        "repair": "reinvoke",
        "circuit_breaker_after": 2,
        "fallback": "discuss",
    },
}

_MERGE_KEYWORDS = re.compile(
    r"merge conflict|conflict|CONFLICT|merge_conflict", re.IGNORECASE
)
_STRUCTURAL_KEYWORDS = frozenset({
    "merge conflict",
    "merge_conflict",
    "worktree",
    "fail closed",
    "fail_closed",
    "structural",
    "isolation_required",
    "isolation_blocked",
    "git root missing",
})
_ORACLE_SKIP_TOKENS = frozenset({
    "",
    "verify field missing",
    "검증 기준 없음",
    "-",
    "—",
    "n/a",
    "none",
})


def classify_failure(
    execution: dict[str, Any],
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify failure code from execution + optional evidence.

    Returns {code: FailureCode, label: str, recoverable: bool, max_repair: int, ...}
    """
    evidence = evidence or {}
    oracle = execution.get("oracle") if isinstance(execution.get("oracle"), dict) else {}
    merge = execution.get("merge") if isinstance(execution.get("merge"), dict) else {}
    reason = (
        str(oracle.get("detail") or "")
        or str(execution.get("blocked_message") or "")
        or str(evidence.get("error") or "")
        or "unknown failure"
    )
    status = str(execution.get("status") or "")

    if status == "blocked_isolation" or execution.get("blocked_reason") in (
        "isolation_blocked",
        "git_root_missing",
        "base_branch_dirty",
    ):
        return _code_meta(FailureCode.ISOLATION_BLOCKED, reason=reason)

    conflict_files = merge.get("conflict_files") or []
    if conflict_files or _MERGE_KEYWORDS.search(reason):
        return _code_meta(FailureCode.MERGE_CONFLICT, reason=reason)

    low = reason.strip().lower()
    if any(token in low for token in _STRUCTURAL_KEYWORDS):
        return _code_meta(FailureCode.STRUCTURAL, reason=reason)

    oracle_detail = (str(oracle.get("detail") or "") or "").strip()
    if oracle_detail and oracle_detail.lower() in _ORACLE_SKIP_TOKENS:
        verdict = str(oracle.get("verdict") or "").strip().lower()
        if verdict == "skipped":
            return _code_meta(FailureCode.ORACLE_SKIP, reason=reason)

    verify_criterion = (str(oracle.get("verify_criterion") or "") or "").strip()
    if verify_criterion and verify_criterion.lower() in _ORACLE_SKIP_TOKENS:
        return _code_meta(FailureCode.ORACLE_SKIP, reason=reason)

    return _code_meta(FailureCode.ORACLE_FAIL, reason=reason)


def policy_for(failure: dict[str, Any]) -> dict[str, Any]:
    code = FailureCode(failure["code"])
    return dict(_POLICY[code])


def repair_counts_key(action_index: int) -> str:
    return str(int(action_index))


def normalize_repair_counts(ml: dict[str, Any]) -> dict[str, Any]:
    raw = ml.get("action_repair_counts") or {}
    if isinstance(raw, dict):
        return {str(k): int(v) for k, v in raw.items()}
    return {}


def worktree_healthy(ew: Any | None) -> bool:
    if ew is None or not getattr(ew.worktree_path, "is_dir", lambda: False)():
        return True
    root = ew.git_root.resolve()
    wt = ew.worktree_path.resolve()
    if wt == root:
        return True

    import subprocess

    r = subprocess.run(
        ["git", "-C", str(wt), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    text = (r.stdout or "").strip()
    if not text:
        return True
    allowed_prefixes = ("??",)
    for line in text.splitlines():
        if not any(line.startswith(prefix) for prefix in allowed_prefixes):
            return False
    return True


def ensure_worktree_usable(
    folder: Path,
    *,
    execution: dict[str, Any],
    exec_id: str,
    mode: str = "default",
    action_key: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Return (ok, result) where result is either refreshed worktree dict or discard result.

    Modes:
      - default: prior best-effort gate behavior, no recreate.
      - recreate: discard unhealthy worktree and recreate it when fields are available.
    """
    if mode not in {"default", "recreate"}:
        raise ValueError(f"unsupported ensure_worktree_usable mode: {mode!r}")
    ew = _execution_worktree(execution)
    if ew is None:
        return True, {"ok": True, "skipped": "no_worktree"}
    if worktree_healthy(ew):
        return True, {"ok": True, "skipped": "healthy"}

    if mode != "recreate":
        discard_exec_worktree(ew, folder, exec_id)
        return False, {"action": "discarded", "exec_id": exec_id}

    try:
        from agent_lab.plan_execute_worktree import (
            ExecWorktree,
            create_exec_worktree,
            discard_exec_worktree,
        )
        from agent_lab.plan_actions import action_key as plan_action_key  # noqa: F401
    except Exception as exc:  # pragma: no cover - defensive import guard
        discard_exec_worktree(ew, folder, exec_id)
        return False, {"action": "discarded", "exec_id": exec_id, "recreate_error": str(exc)}

    discard_exec_worktree(ew, folder, exec_id)

    ak = action_key or execution.get("action_key") or "unknown-action"
    try:
        recreated = create_exec_worktree(
            folder,
            exec_id=exec_id,
            git_root=ew.git_root,
            action_key=ak,
            base_branch=ew.base_branch,
        )
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        return False, {"action": "recreate_failed", "exec_id": exec_id, "error": str(exc)}

    # Re-run health check on the new worktree, and if still unhealthy fall back to discard.
    if not worktree_healthy(recreated):
        discard_exec_worktree(recreated, folder, exec_id)
        return False, {"action": "recreate_unhealthy", "exec_id": exec_id}

    return True, {"ok": True, "recreated": recreated.to_dict()}


# --------------------------------------------------------------------------- #


def _code_meta(code: FailureCode, *, reason: str) -> dict[str, Any]:
    meta = dict(_POLICY[code])
    meta["code"] = code.value
    meta["reason"] = reason
    return meta


def subprocess_exec(args: list[str], *, check: bool = True) -> "subprocess.CompletedProcess[str]":
    import subprocess

    return subprocess.run(args, capture_output=True, text=True, check=check)


def _execution_worktree(execution: dict[str, Any]) -> Any | None:
    required = ("git_root", "worktree_path", "exec_branch", "base_branch", "base_sha")
    if not all(execution.get(key) for key in required):
        return None
    try:
        from agent_lab.plan_execute_worktree import ExecWorktree
    except Exception:
        return None
    return ExecWorktree(
        git_root=Path(str(execution["git_root"])),
        worktree_path=Path(str(execution["worktree_path"])),
        branch=str(execution["exec_branch"]),
        base_branch=str(execution["base_branch"]),
        base_sha=str(execution["base_sha"]),
    )
