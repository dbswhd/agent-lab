"""R2 (05-reliability-evaluation-operations.md) — cancel journey first slice.

R1 (docs/redesign-2026-07/evidence/r1-journey-reliability-matrix-2026-07-16.md
§3) found sessions/_regression/ has no cancel fixture. Digging in further:
plan.execute.cancel_open_execution — the actual execution-level cancel path
(discard an open dry-run/merge-review before it merges) — had zero test
coverage anywhere, not just no golden fixture. test_run_control.py covers a
different concept (subprocess/turn-level request_cancel()), which is why the
R1 doc's "unit test는 있음" undersold the gap; see the correction there.

This covers cancel_open_execution's three branches directly rather than
adding a sessions/_regression/ fixture: the function's persisted run.json
shape after a successful cancel is identical to a manual reject (both go
through resolve_execution(vote="reject")) — worktree_reject/ already covers
that shape. What was actually untested is cancel_open_execution's own
call-site behavior: no-op when nothing is open, no-op when the open
execution isn't in a cancellable status, and the success path's return
envelope (reason="user_cancel", worktree discarded).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_mocks import disable_execute_inbox_mcp

from agent_lab.plan.actions import find_dry_run_action
from agent_lab.plan.execute import cancel_open_execution, run_dry_run
from agent_lab.plan.pending import PlanSnapshotRequired, approve_pending_plan, ensure_plan_snapshot_approved
from agent_lab.run.meta import patch_run_meta, read_run_meta


def _git(cwd: Path, *args: str) -> str:
    import subprocess

    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def _seed_approved_plan_snapshot(folder: Path, plan_md: str) -> None:
    action = find_dry_run_action(plan_md, 1, kind="now")
    assert action is not None
    try:
        ensure_plan_snapshot_approved(folder, action, plan_md)
    except PlanSnapshotRequired as exc:
        approve_pending_plan(folder, exc.pending_plan["id"])


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    return _init_repo(tmp_path / "repo")


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    d = tmp_path / "session"
    d.mkdir()
    return d


def test_cancel_open_execution_skips_when_nothing_is_open(session_folder: Path) -> None:
    (session_folder / "run.json").write_text("{}\n", encoding="utf-8")

    result = cancel_open_execution(session_folder)

    assert result == {"skipped": True, "reason": "no_open_execution"}


def test_cancel_open_execution_skips_when_status_is_not_cancellable(session_folder: Path) -> None:
    (session_folder / "run.json").write_text("{}\n", encoding="utf-8")

    def _seed(run: dict) -> dict:
        run["executions"] = [{"id": "exec-merged", "status": "merged"}]
        return run

    patch_run_meta(session_folder, _seed)

    result = cancel_open_execution(session_folder, execution_id="exec-merged")

    assert result == {"skipped": True, "reason": "not_cancellable", "status": "merged"}


def test_cancel_open_execution_rejects_and_discards_pending_worktree(
    git_repo: Path,
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disable_execute_inbox_mcp(monkeypatch)
    plan_md = """## 지금 실행
1.
   - 무엇을: app.py를 취소한다.
   - 어디서: `src/app.py`
   - 검증: `src/app.py` 내용 확인
"""
    (session_folder / "plan.md").write_text(plan_md, encoding="utf-8")
    (session_folder / "run.json").write_text("{}\n", encoding="utf-8")
    _seed_approved_plan_snapshot(session_folder, plan_md)

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)

    def _respond(**kwargs):
        (Path(kwargs["cwd"]) / "src" / "app.py").write_text("would have merged\n", encoding="utf-8")
        return "VERIFICATION: PASS"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _respond)
    monkeypatch.setattr(
        "agent_lab.plan.execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (git_repo, {}),
    )

    execution = run_dry_run(session_folder, action_index=1, permissions={})
    worktree_path = Path(execution["worktree_path"])
    assert worktree_path.exists()

    result = cancel_open_execution(session_folder, execution_id=execution["id"], reason="user_cancel")

    assert result["status"] == "cancelled"
    assert result["reason"] == "user_cancel"
    assert result["execution_id"] == execution["id"]
    assert result["execution"]["status"] == "rejected"
    assert not worktree_path.exists()

    run = read_run_meta(session_folder)
    row = next(r for r in run["executions"] if r["id"] == execution["id"])
    assert row["status"] == "rejected"
    assert (git_repo / "src" / "app.py").read_text(encoding="utf-8") == "v1\n"
