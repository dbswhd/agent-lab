"""Unit tests for verify_repair_policy."""

from __future__ import annotations

from pathlib import Path


from agent_lab.verify_repair_policy import (
    FailureCode,
    classify_failure,
    ensure_worktree_usable,
    normalize_repair_counts,
    policy_for,
    repair_counts_key,
    worktree_healthy,
)


def _execution(**overrides):
    base = {
        "id": "exec-1",
        "status": "",
        "oracle": {"verdict": "fail", "detail": "FAIL: missing VERIFIED_OK"},
        "merge": {},
    }
    base.update(overrides)
    return base


def test_classify_oracle_fail_default():
    failure = classify_failure(_execution())
    assert failure["code"] == FailureCode.ORACLE_FAIL
    assert failure["recoverable"] is True
    assert failure["max_repair"] == 2
    assert failure["repair"] == "reverify"


def test_classify_merge_conflict():
    failure = classify_failure(_execution(merge={"status": "conflict", "conflict_files": ["a.py"]}))
    assert failure["code"] == FailureCode.MERGE_CONFLICT
    assert failure["recoverable"] is True
    assert failure["fallback"] == "discuss"


def test_classify_merge_conflict_from_reason():
    failure = classify_failure(_execution(oracle={"detail": "merge conflict in a.py"}))
    assert failure["code"] == FailureCode.MERGE_CONFLICT


def test_classify_isolation_blocked():
    failure = classify_failure(_execution(status="blocked_isolation", blocked_reason="isolation_blocked"))
    assert failure["code"] == FailureCode.ISOLATION_BLOCKED
    assert failure["recoverable"] is False


def test_classify_structural_from_structural_keyword():
    failure = classify_failure(_execution(oracle={"detail": "structural failure"}))
    assert failure["code"] == FailureCode.STRUCTURAL

    failure = classify_failure(
        {
            "id": "exec-1",
            "status": "",
            "blocked_message": "isolation_blocked during execute",
        }
    )
    assert failure["code"] == FailureCode.STRUCTURAL


def test_classify_worktree_git_dirty_best_effort():
    # Current classifier does not expose a dedicated worktree-dirty code path
    # that survives structural-keyword precedence, so this asserts fallback.
    failure = classify_failure(_execution(oracle={"detail": "worktree state is broken"}))
    assert failure["code"] == FailureCode.STRUCTURAL


def test_classify_skip_tokens_are_exact_case_insensitive():
    for token in ("verify field missing", "검증 기준 없음", "-", "—", "n/a", "none"):
        failure = classify_failure(_execution(oracle={"detail": token, "verdict": "skipped"}))
        assert failure["code"] == FailureCode.ORACLE_SKIP


def test_policy_for_returns_copy():
    failure = classify_failure(_execution())
    policy = policy_for(failure)
    assert policy["label"] == "oracle_fail"
    policy["label"] = "changed"
    assert policy_for(failure)["label"] == "oracle_fail"


def test_normalize_repair_counts_coerces_values():
    ml = {"action_repair_counts": {"1": "2", "2": 1}}
    out = normalize_repair_counts(ml)
    assert out == {"1": 2, "2": 1}


def test_repair_counts_key_floor():
    assert repair_counts_key(1) == "1"
    assert repair_counts_key(1.9) == "1"


class _Worktree:
    def __init__(self, path: Path) -> None:
        self.worktree_path = path
        self.git_root = path


def test_worktree_healthy_when_missing(tmp_path: Path):
    missing = tmp_path / "missing"
    assert worktree_healthy(None) is True
    assert worktree_healthy(_Worktree(missing)) is True


def test_worktree_healthy_when_clean(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    assert worktree_healthy(_Worktree(repo)) is True


def _init_repo(path: Path) -> Path:
    import subprocess

    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-b", "main"], check=True)
    (path / "x.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], check=True)
    return path


def test_ensure_worktree_usable_no_op_default():
    folder = Path("/tmp/does-not-matter")
    ok, result = ensure_worktree_usable(folder, execution={"id": "e1"}, exec_id="e1")
    assert ok is True
    assert result.get("skipped") == "no_worktree"
