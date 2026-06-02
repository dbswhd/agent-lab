from __future__ import annotations

import subprocess
from pathlib import Path

from agent_lab.plan_actions import find_dry_run_action
from agent_lab.plan_execute_isolation import resolve_action_isolation


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


def _action(plan_md: str):
    action = find_dry_run_action(plan_md, 1, kind="now")
    assert action is not None
    return action


def test_isolation_policy_git_auto_worktree(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    action = _action(
        """## 지금 실행
1.
   - 무엇을: app 수정
   - 어디서: `src/app.py`
   - 검증: pytest
"""
    )

    decision = resolve_action_isolation(action, {}, repo)

    assert decision.isolation == "worktree"
    assert decision.isolation_source == "auto"
    assert decision.git_root == repo.resolve()


def test_isolation_policy_non_git_apply(tmp_path: Path):
    workspace = tmp_path / "plain"
    workspace.mkdir()
    (workspace / "notes.md").write_text("x\n", encoding="utf-8")
    action = _action(
        """## 지금 실행
1.
   - 무엇을: 노트 수정
   - 어디서: `notes.md`
   - 검증: 파일 확인
"""
    )

    decision = resolve_action_isolation(action, {}, workspace)

    assert decision.isolation == "apply"
    assert decision.git_root is None


def test_isolation_policy_multi_root_block(tmp_path: Path):
    a = _init_repo(tmp_path / "repo-a")
    b = _init_repo(tmp_path / "repo-b")
    action = _action(
        f"""## 지금 실행
1.
   - 무엇을: 두 repo 수정
   - 어디서: `{a / "src/app.py"}` `{b / "src/app.py"}`
   - 검증: 테스트
"""
    )

    decision = resolve_action_isolation(action, {}, None)

    assert decision.isolation == "block"
    assert decision.block_reason == "paths_span_repos"


def test_isolation_policy_explicit_block_and_apply(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    block_action = _action(
        """## 지금 실행
1.
   - 무엇을: 명시 차단
   - 어디서: `src/app.py`
   - 검증: 테스트
   - isolation: block
"""
    )
    apply_action = _action(
        """## 지금 실행
1.
   - 무엇을: 명시 apply
   - 어디서: `src/app.py`
   - 검증: 테스트
   - isolation: apply
"""
    )

    block = resolve_action_isolation(block_action, {}, repo)
    apply = resolve_action_isolation(apply_action, {}, repo)

    assert block.isolation == "block"
    assert block.isolation_source == "plan"
    assert block.block_reason == "isolation=block"
    assert apply.isolation == "apply"
    assert apply.isolation_source == "plan"


def test_isolation_policy_override_meta(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    action = _action(
        """## 지금 실행
1.
   - 무엇을: override
   - 어디서: `src/app.py`
   - 검증: 테스트
"""
    )

    decision = resolve_action_isolation(
        action,
        {},
        repo,
        override={"mode": "snapshot_override", "by": "human"},
    )

    assert decision.isolation == "snapshot_override"
    assert decision.isolation_source == "override"
    assert decision.override == {"mode": "snapshot_override", "by": "human"}
