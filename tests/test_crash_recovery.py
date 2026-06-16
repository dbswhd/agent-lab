"""G3 durable crash-recovery: boot-time reconcile of crashed in-flight merges."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent_lab.crash_recovery import reconcile_crashed_merges
from agent_lab.plan_execute_merge import merge_exec_branch
from agent_lab.plan_execute_worktree import create_exec_worktree


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check)
    return r.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def _write_run(folder: Path, run: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(json.dumps(run, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_run(folder: Path) -> dict:
    return json.loads((folder / "run.json").read_text(encoding="utf-8"))


def _exec_row(exec_id: str, *, status: str, checkpoint: dict | None = None, **extra) -> dict:
    row = {"id": exec_id, "status": status, "isolation_effective": "worktree", **extra}
    if checkpoint is not None:
        row["checkpoint"] = checkpoint
    return row


def _checkpoint(ew, *, op: str, exec_commit_sha: str, base_sha_before: str, prev_status: str, prev_merge=None) -> dict:
    return {
        "phase": "merging",
        "op": op,
        "started_at": "2026-01-01T00:00:00+00:00",
        "git_root": str(ew.git_root),
        "worktree_path": str(ew.worktree_path),
        "base_branch": ew.base_branch,
        "base_sha_before": base_sha_before,
        "exec_branch": ew.branch,
        "exec_commit_sha": exec_commit_sha,
        "prev_status": prev_status,
        "prev_merge": prev_merge or {},
        "snapshot_id": "",
    }


@pytest.fixture
def sessions_root(tmp_path: Path) -> Path:
    root = tmp_path / "sessions"
    root.mkdir()
    return root


def _make_worktree(sess: Path, repo: Path, *, exec_id: str, edit: bool = True):
    ew = create_exec_worktree(
        sess, exec_id=exec_id, git_root=repo, action_key="now:1", session_id=sess.name
    )
    if edit:
        (ew.worktree_path / "src" / "app.py").write_text("v2\n", encoding="utf-8")
        _git(ew.worktree_path, "add", "-A")
        _git(ew.worktree_path, "commit", "-m", "exec change")
    exec_sha = _git(ew.worktree_path, "rev-parse", "HEAD")
    return ew, exec_sha


def test_reconcile_landed_merge_marks_merged(sessions_root: Path, tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    sess = sessions_root / "sess"
    sess.mkdir()
    base_before = _git(repo, "rev-parse", "main")
    ew, exec_sha = _make_worktree(sess, repo, exec_id="exec-1")
    # Simulate the irreversible merge actually landing (and worktree removal),
    # but the status persist never happened → run.json still pending_approval.
    merge_exec_branch(ew, session_folder=sess, exec_id="exec-1")
    base_head = _git(repo, "rev-parse", "main")
    cp = _checkpoint(ew, op="merge", exec_commit_sha=exec_sha, base_sha_before=base_before, prev_status="pending_approval")
    _write_run(sess, {"executions": [_exec_row("exec-1", status="pending_approval", checkpoint=cp)]})

    summary = reconcile_crashed_merges(sessions_root=sessions_root)

    assert summary["reconciled_merged"] == 1
    row = _read_run(sess)["executions"][0]
    assert row["status"] == "merged"
    assert row["merge"]["commit_sha"] == base_head
    assert row["merge"]["recovered"] is True
    assert "checkpoint" not in row
    inbox = _read_run(sess).get("human_inbox") or []
    assert len(inbox) == 1 and inbox[0]["source"] == "crash_recovery:exec-1"


def test_rollback_when_merge_never_landed(sessions_root: Path, tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    sess = sessions_root / "sess"
    sess.mkdir()
    base_before = _git(repo, "rev-parse", "main")
    ew, exec_sha = _make_worktree(sess, repo, exec_id="exec-1")
    # Crash BEFORE merge landed: base unchanged, worktree still present.
    cp = _checkpoint(ew, op="merge", exec_commit_sha=exec_sha, base_sha_before=base_before, prev_status="pending_approval")
    _write_run(sess, {"executions": [_exec_row("exec-1", status="pending_approval", checkpoint=cp)]})

    summary = reconcile_crashed_merges(sessions_root=sessions_root)

    assert summary["rolled_back"] == 1
    row = _read_run(sess)["executions"][0]
    assert row["status"] == "pending_approval"
    assert "checkpoint" not in row
    assert ew.worktree_path.is_dir()  # worktree preserved for re-approval


def test_rollback_restores_prev_status_confirm(sessions_root: Path, tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    sess = sessions_root / "sess"
    sess.mkdir()
    base_before = _git(repo, "rev-parse", "main")
    ew, exec_sha = _make_worktree(sess, repo, exec_id="exec-1")
    prev_merge = {"status": "conflict", "conflict_files": ["src/app.py"]}
    cp = _checkpoint(
        ew, op="confirm", exec_commit_sha=exec_sha, base_sha_before=base_before,
        prev_status="merge_conflict", prev_merge=prev_merge,
    )
    _write_run(sess, {"executions": [_exec_row("exec-1", status="merge_conflict", checkpoint=cp)]})

    reconcile_crashed_merges(sessions_root=sessions_root)

    row = _read_run(sess)["executions"][0]
    assert row["status"] == "merge_conflict"  # restored verbatim, not hardcoded
    assert row["merge"] == prev_merge


def test_quarantine_when_git_root_missing(sessions_root: Path, tmp_path: Path):
    sess = sessions_root / "sess"
    sess.mkdir()
    cp = {
        "phase": "merging", "op": "merge", "git_root": str(tmp_path / "nope"),
        "base_branch": "main", "base_sha_before": "abc", "exec_branch": "x",
        "exec_commit_sha": "def", "prev_status": "pending_approval", "prev_merge": {},
    }
    _write_run(sess, {"executions": [_exec_row("exec-1", status="pending_approval", checkpoint=cp)]})

    summary = reconcile_crashed_merges(sessions_root=sessions_root)

    assert summary["quarantined"] == 1 and summary["errors"] == 0
    row = _read_run(sess)["executions"][0]
    assert row["checkpoint"]["recovery"] == "undeterminable"
    assert row["status"] == "pending_approval"  # unchanged


def test_quarantine_ambiguous_noop(sessions_root: Path, tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    sess = sessions_root / "sess"
    sess.mkdir()
    base_head = _git(repo, "rev-parse", "main")
    # exec_commit == base head (trivially an ancestor) AND base did not move.
    cp = {
        "phase": "merging", "op": "merge", "git_root": str(repo),
        "base_branch": "main", "base_sha_before": base_head, "exec_branch": "main",
        "exec_commit_sha": base_head, "prev_status": "pending_approval", "prev_merge": {},
    }
    _write_run(sess, {"executions": [_exec_row("exec-1", status="pending_approval", checkpoint=cp)]})

    summary = reconcile_crashed_merges(sessions_root=sessions_root)

    assert summary["quarantined"] == 1
    row = _read_run(sess)["executions"][0]
    assert row["checkpoint"]["recovery"] == "ambiguous_noop"
    assert row["status"] == "pending_approval"


def test_idempotent_double_run(sessions_root: Path, tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    sess = sessions_root / "sess"
    sess.mkdir()
    base_before = _git(repo, "rev-parse", "main")
    ew, exec_sha = _make_worktree(sess, repo, exec_id="exec-1")
    merge_exec_branch(ew, session_folder=sess, exec_id="exec-1")
    cp = _checkpoint(ew, op="merge", exec_commit_sha=exec_sha, base_sha_before=base_before, prev_status="pending_approval")
    _write_run(sess, {"executions": [_exec_row("exec-1", status="pending_approval", checkpoint=cp)]})

    first = reconcile_crashed_merges(sessions_root=sessions_root)
    second = reconcile_crashed_merges(sessions_root=sessions_root)

    assert first["reconciled_merged"] == 1
    assert second["reconciled_merged"] == 0
    assert len(_read_run(sess).get("human_inbox") or []) == 1  # no duplicate notice


def test_no_checkpoint_rows_are_noop(sessions_root: Path, tmp_path: Path):
    sess = sessions_root / "sess"
    sess.mkdir()
    _write_run(sess, {"executions": [
        _exec_row("e1", status="merged"),
        _exec_row("e2", status="pending_approval"),
    ]})

    summary = reconcile_crashed_merges(sessions_root=sessions_root)

    assert summary["scanned"] == 1
    assert summary["reconciled_merged"] == summary["rolled_back"] == summary["quarantined"] == 0


def test_pre_feature_pending_with_attempted_at_quarantines(sessions_root: Path, tmp_path: Path):
    sess = sessions_root / "sess"
    sess.mkdir()
    _write_run(sess, {"executions": [
        _exec_row("e1", status="pending_approval", merge={"status": "pending", "attempted_at": "2026-01-01T00:00:00+00:00"}),
    ]})

    summary = reconcile_crashed_merges(sessions_root=sessions_root)

    assert summary["quarantined"] == 1
    row = _read_run(sess)["executions"][0]
    assert row["recovery"]["action"] == "quarantined"
    assert row["recovery"]["reason"] == "pre_feature_no_checkpoint"


def test_one_bad_session_does_not_abort_scan(sessions_root: Path, tmp_path: Path):
    # Bad session: corrupt run.json that read_run_meta cannot parse cleanly enough
    # to reconcile (forces the per-session except path).
    bad = sessions_root / "bad"
    bad.mkdir()
    (bad / "run.json").write_text("{ this is not json", encoding="utf-8")
    # Also seed a checkpoint that will make patch validation fail (invalid sibling status).
    repo = _init_repo(tmp_path / "repo")
    good = sessions_root / "good"
    good.mkdir()
    base_before = _git(repo, "rev-parse", "main")
    ew, exec_sha = _make_worktree(good, repo, exec_id="exec-1")
    merge_exec_branch(ew, session_folder=good, exec_id="exec-1")
    cp = _checkpoint(ew, op="merge", exec_commit_sha=exec_sha, base_sha_before=base_before, prev_status="pending_approval")
    _write_run(good, {"executions": [_exec_row("exec-1", status="pending_approval", checkpoint=cp)]})

    summary = reconcile_crashed_merges(sessions_root=sessions_root)

    # Good session reconciled regardless of the bad one; scan never raised.
    assert summary["reconciled_merged"] == 1
    assert _read_run(good)["executions"][0]["status"] == "merged"


def test_repair_merge_checkpoint_landed(sessions_root: Path, tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    sess = sessions_root / "sess"
    sess.mkdir()
    base_before = _git(repo, "rev-parse", "main")
    ew, exec_sha = _make_worktree(sess, repo, exec_id="exec-1")
    merge_exec_branch(ew, session_folder=sess, exec_id="exec-1")
    base_head = _git(repo, "rev-parse", "main")
    cp = _checkpoint(ew, op="repair_merge", exec_commit_sha=exec_sha, base_sha_before=base_before, prev_status="merged")
    _write_run(sess, {"executions": [_exec_row("exec-1", status="merged", checkpoint=cp)]})

    summary = reconcile_crashed_merges(sessions_root=sessions_root)

    assert summary["reconciled_merged"] == 1
    row = _read_run(sess)["executions"][0]
    assert row["status"] == "merged"
    assert row["merge"]["commit_sha"] == base_head
    assert row["recovery"]["op"] == "repair_merge"
