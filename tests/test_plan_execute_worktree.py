"""M0 spike: git worktree create, discard, merge."""

from __future__ import annotations

import subprocess
import json
from pathlib import Path

import pytest

from agent_lab.plan_actions import find_dry_run_action
from agent_lab.plan_execute import resolve_execution, run_dry_run
from agent_lab.plan_pending import (
    PlanSnapshotRequired,
    approve_pending_plan,
    ensure_plan_snapshot_approved,
)
from agent_lab.plan_execute_git import (
    detect_git_root,
    git_root_for_paths,
    resolve_action_git_context,
)
from agent_lab.plan_execute_merge import MergeConflict, merge_exec_branch
from agent_lab.plan_execute_worktree import (
    WorktreeUnavailable,
    create_exec_worktree,
    discard_exec_worktree,
)


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=check,
    )
    return r.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def _commit_all(wt: Path, msg: str) -> None:
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", msg)


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


def test_detect_git_root(git_repo: Path):
    assert detect_git_root(git_repo / "src" / "app.py") == git_repo.resolve()


def test_rewrite_git_paths_in_text(git_repo: Path):
    from agent_lab.plan_execute import _rewrite_git_paths_in_text

    app = git_repo / "src" / "app.py"
    raw = f"edit `{app}` and check {app.resolve()}"
    out = _rewrite_git_paths_in_text(raw, git_root=git_repo)
    assert str(git_repo) not in out
    assert "src/app.py" in out


def test_resolve_action_worktree(git_repo: Path):
    ctx = resolve_action_git_context(
        action_key="now:1",
        monitored_paths=["src/app.py"],
        cwd_hint=git_repo,
    )
    assert ctx.isolation == "worktree"
    assert ctx.git_root == git_repo.resolve()


def test_resolve_action_apply_non_git(tmp_path: Path):
    d = tmp_path / "plain"
    d.mkdir()
    (d / "notes.md").write_text("x", encoding="utf-8")
    ctx = resolve_action_git_context(
        action_key="now:1",
        monitored_paths=["notes.md"],
        cwd_hint=d,
    )
    assert ctx.isolation == "apply"
    assert ctx.git_root is None


def test_worktree_merge_ok(git_repo: Path, session_folder: Path):
    exec_id = "exec-merge01"
    ew = create_exec_worktree(
        session_folder,
        exec_id=exec_id,
        git_root=git_repo,
        action_key="now:1",
        session_id="sess-test",
    )
    assert ew.worktree_path.is_dir()
    assert detect_git_root(git_repo) == git_repo.resolve()
    assert _git(git_repo, "status", "--porcelain") == ""

  # simulate Cursor patch in isolated tree
    target = ew.worktree_path / "src" / "app.py"
    target.write_text("v2\n", encoding="utf-8")
    _commit_all(ew.worktree_path, "agent-lab dry-run")

    result = merge_exec_branch(
        ew,
        session_folder=session_folder,
        exec_id=exec_id,
        message="agent-lab: test merge",
    )
    assert result.status == "merged"
    assert result.commit_sha
    assert (git_repo / "src" / "app.py").read_text(encoding="utf-8") == "v2\n"
    assert not ew.worktree_path.exists()
    assert _git(git_repo, "branch", "--list", "agent-lab/*", check=False) == ""


def test_worktree_reject_main_unchanged(git_repo: Path, session_folder: Path):
    exec_id = "exec-reject1"
    before = (git_repo / "src" / "app.py").read_text(encoding="utf-8")
    ew = create_exec_worktree(
        session_folder,
        exec_id=exec_id,
        git_root=git_repo,
        action_key="now:2",
        session_id="sess-test",
    )
    (ew.worktree_path / "src" / "app.py").write_text("should not land\n", encoding="utf-8")
    _commit_all(ew.worktree_path, "wip")

    discard_exec_worktree(ew, session_folder, exec_id)

    assert (git_repo / "src" / "app.py").read_text(encoding="utf-8") == before
    assert not ew.worktree_path.exists()


def test_worktree_blocked_dirty_main(git_repo: Path, session_folder: Path):
    (git_repo / "src" / "app.py").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(WorktreeUnavailable) as exc:
        create_exec_worktree(
            session_folder,
            exec_id="exec-dirty",
            git_root=git_repo,
            action_key="now:1",
        )
    assert exc.value.reason == "base_branch_dirty"


def test_paths_span_repos_blocked(tmp_path: Path):
    a = _init_repo(tmp_path / "repo-a")
    b = _init_repo(tmp_path / "repo-b")
    ctx = resolve_action_git_context(
        action_key="now:1",
        monitored_paths=[str(a / "src" / "app.py"), str(b / "src" / "app.py")],
    )
    assert ctx.isolation == "block"
    assert git_root_for_paths(
        [str(a / "src" / "app.py"), str(b / "src" / "app.py")]
    ) is None


def test_run_dry_run_worktree_cwd_and_record(
    git_repo: Path,
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plan_md = """## 지금 실행
1.
   - 무엇을: app.py를 v2로 수정한다.
   - 어디서: `src/app.py`
   - 검증: `src/app.py` 내용 확인
"""
    (session_folder / "plan.md").write_text(plan_md, encoding="utf-8")
    (session_folder / "run.json").write_text("{}\n", encoding="utf-8")
    _seed_approved_plan_snapshot(session_folder, plan_md)

    seen_cwd: list[Path] = []

    def _respond(**kwargs):
        cwd = Path(kwargs["cwd"])
        seen_cwd.append(cwd)
        assert cwd != git_repo
        assert detect_git_root(cwd) == cwd.resolve()
        (cwd / "src" / "app.py").write_text("v2\n", encoding="utf-8")
        return "VERIFICATION: PASS"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _respond)
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (git_repo, {}),
    )

    execution = run_dry_run(session_folder, action_index=1, permissions={})

    assert seen_cwd and seen_cwd[0] == Path(execution["worktree_path"])
    assert execution["isolation_effective"] == "worktree"
    assert execution["status"] == "pending_approval"
    assert execution["git_root"] == str(git_repo.resolve())
    assert execution["exec_branch"].startswith("agent-lab/")
    assert execution["exec_commit_sha"]
    assert execution["workspace_root"] == execution["worktree_path"]
    assert (git_repo / "src" / "app.py").read_text(encoding="utf-8") == "v1\n"
    assert _git(Path(execution["worktree_path"]), "status", "--porcelain") == ""


def test_resolve_approve_merges_worktree_execution(
    git_repo: Path,
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plan_md = """## 지금 실행
1.
   - 무엇을: app.py를 merge한다.
   - 어디서: `src/app.py`
   - 검증: `src/app.py` 내용 확인
"""
    (session_folder / "plan.md").write_text(plan_md, encoding="utf-8")
    (session_folder / "run.json").write_text("{}\n", encoding="utf-8")
    _seed_approved_plan_snapshot(session_folder, plan_md)

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    def _respond_merge(**kwargs):
        (Path(kwargs["cwd"]) / "src" / "app.py").write_text("v2\n", encoding="utf-8")
        return "VERIFICATION: PASS"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _respond_merge)
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (git_repo, {}),
    )

    execution = run_dry_run(session_folder, action_index=1, permissions={})
    worktree_path = Path(execution["worktree_path"])
    result = resolve_execution(
        session_folder,
        execution_id=execution["id"],
        vote="approve",
        permissions={},
    )

    assert result["execution"]["status"] == "merged"
    assert result["execution"]["merge"]["status"] == "merged"
    assert result["execution"]["merge"]["commit_sha"]
    assert (git_repo / "src" / "app.py").read_text(encoding="utf-8") == "v2\n"
    assert not worktree_path.exists()
    assert _git(git_repo, "branch", "--list", "agent-lab/*", check=False) == ""


def test_resolve_reject_discards_worktree_execution(
    git_repo: Path,
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plan_md = """## 지금 실행
1.
   - 무엇을: app.py를 discard한다.
   - 어디서: `src/app.py`
   - 검증: `src/app.py` 내용 확인
"""
    (session_folder / "plan.md").write_text(plan_md, encoding="utf-8")
    (session_folder / "run.json").write_text("{}\n", encoding="utf-8")
    _seed_approved_plan_snapshot(session_folder, plan_md)

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    def _respond_reject(**kwargs):
        (Path(kwargs["cwd"]) / "src" / "app.py").write_text(
            "discard me\n",
            encoding="utf-8",
        )
        return "VERIFICATION: PASS"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _respond_reject)
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (git_repo, {}),
    )

    execution = run_dry_run(session_folder, action_index=1, permissions={})
    worktree_path = Path(execution["worktree_path"])
    result = resolve_execution(
        session_folder,
        execution_id=execution["id"],
        vote="reject",
        permissions={},
    )

    assert result["execution"]["status"] == "rejected"
    assert (git_repo / "src" / "app.py").read_text(encoding="utf-8") == "v1\n"
    assert not worktree_path.exists()


def test_dry_run_worktree_failure_records_blocked_no_snapshot_degrade(
    git_repo: Path,
    session_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plan_md = """## 지금 실행
1.
   - 무엇을: dirty main에서 실행을 막는다.
   - 어디서: `src/app.py`
   - 검증: 차단 확인
"""
    (session_folder / "plan.md").write_text(plan_md, encoding="utf-8")
    (session_folder / "run.json").write_text("{}\n", encoding="utf-8")
    _seed_approved_plan_snapshot(session_folder, plan_md)
    (git_repo / "src" / "app.py").write_text("dirty\n", encoding="utf-8")

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (git_repo, {}),
    )

    with pytest.raises(WorktreeUnavailable) as exc:
        run_dry_run(session_folder, action_index=1, permissions={})

    assert exc.value.reason == "base_branch_dirty"
    run = json.loads((session_folder / "run.json").read_text(encoding="utf-8"))
    assert run["executions"][-1]["status"] == "blocked_isolation"
    assert run["executions"][-1]["isolation_effective"] == "worktree"
    assert not (session_folder / ".execute-snapshots").exists()
    assert not (session_folder / "worktrees").exists()
