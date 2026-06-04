from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent_lab.plan_execute import (
    MAX_VERIFY_RETRIES,
    abort_merge_execution,
    execution_allows_task_complete,
    reverify_merged_execution,
)
from agent_lab.plan_execute_worktree import list_orphan_worktrees


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def _failed_execution(repo: Path, *, retries: int = 0) -> dict:
    return {
        "id": "exec-repair",
        "status": "merged",
        "isolation_effective": "worktree",
        "executor": "cursor",
        "action_id": "plan-action-now-1",
        "action_index": 1,
        "action_kind": "now",
        "action_key": "now:1",
        "action_what": "add verified marker",
        "action_where": "`src/app.py`",
        "action_verify": "`src/app.py` contains `VERIFIED_OK`",
        "git_root": str(repo.resolve()),
        "workspace_root": str(repo.resolve()),
        "base_branch": "main",
        "base_sha": _git(repo, "rev-parse", "HEAD"),
        "source_touched_paths": ["src/app.py"],
        "touched_paths": ["src/app.py"],
        "expected_paths": ["src/app.py"],
        "verify_retries": retries,
        "verify_after_merge": {
            "status": "failed",
            "verify_retries": retries,
            "source": "mock_oracle",
            "oracle": {
                "verdict": "fail",
                "detail": "FAIL: missing expected literal(s): VERIFIED_OK",
                "checked_paths": ["src/app.py"],
            },
        },
        "oracle": {
            "verdict": "fail",
            "detail": "FAIL: missing expected literal(s): VERIFIED_OK",
            "checked_paths": ["src/app.py"],
        },
        "verify_history": [
            {
                "attempt": retries,
                "status": "failed",
                "oracle": {"verdict": "fail"},
            }
        ],
    }


def _write_run(folder: Path, execution: dict) -> None:
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps(
            {
                "executions": [execution],
                "tasks": [
                    {
                        "id": "task-repair",
                        "title": "add verified marker",
                        "status": "in_progress",
                        "plan_action_index": 1,
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("agent_id", ["cursor", "codex"])
def test_agent_repair_worktree_remerges_and_passes_oracle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_id: str,
):
    repo = _init_repo(tmp_path / "repo")
    folder = tmp_path / "session"
    execution = _failed_execution(repo)
    _write_run(folder, execution)
    seen_cwd: list[Path] = []

    monkeypatch.setattr(
        "agent_lab.agents.registry.available_agents",
        lambda: [agent_id],
    )

    def _repair_cursor(**kwargs):
        cwd = Path(kwargs["cwd"])
        seen_cwd.append(cwd)
        (cwd / "src" / "app.py").write_text("v1\nVERIFIED_OK\n", encoding="utf-8")
        return "VERIFICATION: PASS — repaired"

    def _repair_codex(*_args, **kwargs):
        cwd = Path(kwargs["permissions"]["_discuss_cwd"])
        seen_cwd.append(cwd)
        (cwd / "src" / "app.py").write_text("v1\nVERIFIED_OK\n", encoding="utf-8")
        return "VERIFICATION: PASS — repaired"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _repair_cursor)
    monkeypatch.setattr("agent_lab.agents.codex_agent.respond", _repair_codex)

    result = reverify_merged_execution(
        folder,
        execution_id=execution["id"],
        permissions={"codex": {"cli": True}},
        executor=agent_id,
    )

    repaired = result["execution"]
    assert result["repair"]["agent"] == agent_id
    assert result["repair"]["status"] == "merged"
    assert repaired["verify_retries"] == 1
    assert repaired["oracle"]["verdict"] == "pass"
    assert repaired["verify_after_merge"]["status"] == "passed"
    assert repaired["repair_history"][0]["oracle_after"]["verdict"] == "pass"
    assert len(repaired["verify_history"]) == 2
    assert seen_cwd and seen_cwd[0] != repo
    assert not seen_cwd[0].exists()
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "v1\nVERIFIED_OK\n"
    assert _git(repo, "status", "--porcelain") == ""
    assert _git(repo, "branch", "--list", "agent-lab/*", check=False) == ""
    persisted = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert persisted["tasks"][0]["status"] == "completed"


def test_agent_repair_stops_at_max_verify_retries(
    tmp_path: Path,
):
    repo = _init_repo(tmp_path / "repo")
    folder = tmp_path / "session"
    execution = _failed_execution(repo, retries=MAX_VERIFY_RETRIES)
    _write_run(folder, execution)

    with pytest.raises(ValueError, match="verify retry limit reached"):
        reverify_merged_execution(folder, execution_id=execution["id"])


def test_agent_repair_conflict_keeps_registered_worktree_until_abort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _init_repo(tmp_path / "repo")
    folder = tmp_path / "session"
    execution = _failed_execution(repo)
    _write_run(folder, execution)
    monkeypatch.setattr(
        "agent_lab.agents.registry.available_agents",
        lambda: ["cursor"],
    )

    def _repair(**kwargs):
        cwd = Path(kwargs["cwd"])
        (cwd / "src" / "app.py").write_text("repair\nVERIFIED_OK\n", encoding="utf-8")
        (repo / "src" / "app.py").write_text("concurrent base change\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "concurrent base change")
        return "VERIFICATION: PASS — repaired"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _repair)

    result = reverify_merged_execution(folder, execution_id=execution["id"])

    repaired = result["execution"]
    worktree = Path(repaired["worktree_path"])
    persisted = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert repaired["status"] == "merge_conflict"
    assert repaired["verify_retries"] == 1
    assert result["repair"]["status"] == "merge_conflict"
    assert worktree.name == execution["id"]
    assert worktree.is_dir()
    assert list_orphan_worktrees(folder, persisted) == []

    aborted = abort_merge_execution(folder, execution_id=execution["id"])
    assert aborted["execution"]["status"] == "rejected"
    assert not worktree.exists()
    assert _git(repo, "status", "--porcelain") == ""


def test_oracle_fail_blocks_linked_task_completion(tmp_path: Path):
    repo = _init_repo(tmp_path / "repo")
    execution = _failed_execution(repo)

    assert execution_allows_task_complete(execution) is False
