from __future__ import annotations

"""Shared execute helpers — worktree, git, merge prep (F9)."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunState

from agent_lab.plan.actions import PlanAction
from agent_lab.plan.execute_git import _run_git
from agent_lab.plan.execute_merge import MergeConflict, merge_exec_branch
from agent_lab.plan.execute_paths import paths_relative_to_workspace
from agent_lab.plan.execute_snapshot import delete_snapshot, restore_snapshot
from agent_lab.plan.execute_status import _find_execution
from agent_lab.plan.execute_worktree import ExecWorktree, WorktreeUnavailable, discard_exec_worktree
from agent_lab.plan.execute_verify import (
    _arm_merge_checkpoint,
    _clear_merge_checkpoint,
    _notify_merge_conflict_mission,
    _record_verify_after_merge,
)
from agent_lab.run.meta import patch_run_meta, read_run_meta


import agent_lab.plan.execute as plan_execute


MAX_DIFF_CHARS = 120_000
MAX_VERIFY_RETRIES = 2
from agent_lab.plan.execution_status_scopes import PENDING_STATUS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exec_id() -> str:
    return f"exec-{uuid.uuid4().hex[:12]}"


def _preflight_execute_workspace(
    action: PlanAction,
    permissions: dict[str, Any] | None,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Validate expected paths resolve under the chosen execute workspace."""
    monitored = action.monitored_paths()
    cwd, effective_permissions = plan_execute.resolve_execute_workspace(permissions, monitored)
    info = plan_execute.workspace_path_info(cwd, monitored)
    return cwd, effective_permissions, info


def _worktree_paths(
    paths: list[str],
    *,
    git_root: Path,
) -> list[str]:
    root = git_root.resolve()
    out: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_absolute():
            out.append(path.resolve().relative_to(root).as_posix())
        else:
            out.append(raw)
    return out


def _rewrite_git_paths_in_text(text: str, *, git_root: Path) -> str:
    """Strip absolute git-root prefixes so Cursor edits the worktree cwd, not main."""
    if not text.strip():
        return text
    root = git_root.resolve()
    variants = {root.as_posix(), str(root)}
    out = text
    for prefix in variants:
        if not prefix:
            continue
        out = out.replace(prefix + "/", "")
        if out.endswith(prefix):
            out = out[: -len(prefix)] + "."
    return out


def _workspace_info_for(cwd: Path, raw_paths: list[str]) -> dict[str, Any]:
    return plan_execute.workspace_path_info(cwd, raw_paths)


def _exec_worktree_from_execution(target: dict[str, Any]) -> ExecWorktree:
    missing = [
        key for key in ("git_root", "worktree_path", "exec_branch", "base_branch", "base_sha") if not target.get(key)
    ]
    if missing:
        raise ValueError(f"execution missing worktree metadata: {', '.join(missing)}")
    return ExecWorktree(
        git_root=Path(str(target["git_root"])),
        worktree_path=Path(str(target["worktree_path"])),
        branch=str(target["exec_branch"]),
        base_branch=str(target["base_branch"]),
        base_sha=str(target["base_sha"]),
    )


def _hook_failure_detail(report: dict[str, Any], *, fallback: str) -> str:
    failed = next(
        (row for row in report.get("results") or [] if not row.get("ok")),
        None,
    )
    if isinstance(failed, dict):
        return str(failed.get("detail") or failed.get("cmd") or fallback)
    return fallback


def _worktree_hooks_setup(
    exec_worktree: ExecWorktree,
    *,
    folder: Path,
    exec_id: str,
) -> dict[str, Any]:
    """After worktree create: include copy → create hooks → setup hooks."""
    from agent_lab.worktree_hooks import (
        apply_worktree_include,
        public_config_summary,
        run_worktree_create,
        run_worktree_setup,
    )

    block: dict[str, Any] = {}
    include_report = apply_worktree_include(
        git_root=exec_worktree.git_root,
        worktree_path=exec_worktree.worktree_path,
    )
    if include_report.get("patterns"):
        block["include"] = include_report

    summary = public_config_summary(
        exec_worktree.git_root,
        include_report=include_report,
    )
    if summary:
        block["config_summary"] = summary

    create_report = run_worktree_create(
        worktree_path=exec_worktree.worktree_path,
        git_root=exec_worktree.git_root,
    )
    if create_report is not None:
        if not create_report.get("ok"):
            discard_exec_worktree(exec_worktree, folder, exec_id)
            raise WorktreeUnavailable(
                f"worktree create hooks failed: {_hook_failure_detail(create_report, fallback='create failed')}",
                reason="worktree_create_failed",
                execution_id=exec_id,
            )
        block["create"] = create_report

    setup_report = run_worktree_setup(
        worktree_path=exec_worktree.worktree_path,
        git_root=exec_worktree.git_root,
    )
    if setup_report is None:
        return block
    if not setup_report.get("ok"):
        discard_exec_worktree(exec_worktree, folder, exec_id)
        raise WorktreeUnavailable(
            f"worktree setup hooks failed: {_hook_failure_detail(setup_report, fallback='setup failed')}",
            reason="worktree_setup_failed",
            execution_id=exec_id,
        )
    block["setup"] = setup_report
    return block


def _worktree_hooks_verify_before_merge(
    target: dict[str, Any],
    *,
    execution_id: str,
) -> None:
    if target.get("isolation_effective") != "worktree":
        return
    wt_path = target.get("worktree_path")
    git_root = target.get("git_root")
    if not wt_path or not git_root:
        return
    from agent_lab.worktree_hooks import run_worktree_verify

    verify_report = run_worktree_verify(
        worktree_path=Path(str(wt_path)),
        git_root=Path(str(git_root)),
    )
    if verify_report is None:
        return
    hooks = dict(target.get("worktree_hooks") or {})
    hooks["verify"] = verify_report
    target["worktree_hooks"] = hooks
    if not verify_report.get("ok"):
        raise ValueError(
            f"worktree verify hooks failed: {_hook_failure_detail(verify_report, fallback='verify failed')}",
        )


def _commit_exec_worktree(
    *,
    worktree_path: Path,
    action: PlanAction,
    exec_id: str,
) -> str | None:
    _run_git(worktree_path, "add", "-A")
    has_changes = _run_git(worktree_path, "diff", "--cached", "--quiet", check=False)
    if has_changes.returncode == 0:
        return None
    message = f"agent-lab: dry-run {action.kind}:{action.index} ({exec_id})"
    _run_git(worktree_path, "commit", "-m", message)
    return _run_git(worktree_path, "rev-parse", "HEAD").stdout.strip()


def _merge_commit_message(target: dict[str, Any], *, session_id: str) -> str:
    action = str(target.get("action_what") or target.get("action_key") or "plan action")
    action_key = str(target.get("action_key") or "unknown")
    exec_id = str(target.get("id") or "")
    refs = target.get("provenance_refs") or []
    if not refs:
        refs = [f"plan_action:{target.get('action_index')}"]
    refs_text = "; ".join(str(ref) for ref in refs if ref)
    lines = [
        f"agent-lab: {action} ({action_key})",
        "",
        f"Session: {session_id}",
        f"Execution: {exec_id}",
    ]
    if refs_text:
        lines.append(f"Refs: {refs_text}")
    lines.append("Approved-by: human")
    return "\n".join(lines)


def _commit_repair_worktree(
    worktree_path: Path,
    *,
    target: dict[str, Any],
    attempt: int,
) -> str | None:
    _run_git(worktree_path, "add", "-A")
    has_changes = _run_git(worktree_path, "diff", "--cached", "--quiet", check=False)
    if has_changes.returncode == 0:
        return None
    action_key = str(target.get("action_key") or "plan-action")
    _run_git(
        worktree_path,
        "commit",
        "-m",
        f"agent-lab: repair {action_key} attempt {attempt}",
    )
    return _run_git(worktree_path, "rev-parse", "HEAD").stdout.strip()


def _resolve_reject(
    folder: Path,
    target: dict[str, Any],
    *,
    manifest: dict[str, Any] | None,
    snapshot_id: str,
    cwd: Path,
    execution_id: str,
    completed: str,
) -> None:
    """Reject path: restore snapshot, discard worktree, mark rejected, revert tasks."""
    if manifest is not None:
        restore_snapshot(folder, exec_id=snapshot_id, cwd=cwd, manifest=manifest)
        delete_snapshot(folder, snapshot_id)
    if target.get("isolation_effective") == "worktree":
        discard_exec_worktree(_exec_worktree_from_execution(target), folder, execution_id)
    target["status"] = "rejected"
    target["completed_at"] = completed

    def _revert_tasks(run: RunState) -> RunState:
        from agent_lab.room.tasks import revert_tasks_for_rejected_execution

        revert_tasks_for_rejected_execution(
            run,
            action_index=target.get("action_index"),
            action_id=target.get("action_id"),
            execution_id=execution_id,
        )
        return run

    patch_run_meta(folder, _revert_tasks)


def _resolve_snapshot_paths(target: dict[str, Any], cwd: Any) -> tuple[list[str], list[str], list[str], str]:
    """Reconstruct snapshot/source/artifact paths and snapshot id from the execution row."""
    snapshot_paths = list(target.get("snapshot_paths") or [])
    if not snapshot_paths:
        raw_monitored = list(
            target.get("monitored_paths") or target.get("snapshotted_paths") or target.get("expected_paths") or []
        )
        snapshot_paths = paths_relative_to_workspace(cwd, raw_monitored)
    source_snapshot = list(target.get("source_snapshot_paths") or [])
    if not source_snapshot:
        raw_source = list(target.get("expected_paths") or [])
        source_snapshot = paths_relative_to_workspace(cwd, raw_source)
    artifact_snapshot = list(target.get("artifact_snapshot_paths") or [])
    if not artifact_snapshot:
        raw_verify = list(target.get("verification_paths") or [])
        artifact_snapshot = paths_relative_to_workspace(cwd, raw_verify)
    snapshot_id = str(target.get("snapshot_id") or target.get("id") or "")
    return snapshot_paths, source_snapshot, artifact_snapshot, snapshot_id


def _do_worktree_merge(
    folder: Path,
    execution_id: str,
    target: dict[str, Any],
    completed: str,
) -> None:
    """worktree merge 시도. target을 in-place 변경(status, merge, completed_at)."""
    merge = dict(target.get("merge") or {})
    merge["attempted_at"] = completed
    _arm_merge_checkpoint(folder, execution_id=execution_id, target=target, op="merge")
    try:
        merge_result = merge_exec_branch(
            _exec_worktree_from_execution(target),
            session_folder=folder,
            exec_id=execution_id,
            message=_merge_commit_message(target, session_id=folder.name),
        )
    except MergeConflict as e:
        merge["status"] = "conflict"
        merge["conflict_files"] = e.conflict_files
        merge["completed_at"] = _now()
        target["merge"] = merge
        target["status"] = "merge_conflict"
        target["completed_at"] = merge["completed_at"]
        _clear_merge_checkpoint(target)
        _notify_merge_conflict_mission(folder, target)
    else:
        merge.update(merge_result.to_dict())
        merge["completed_at"] = _now()
        target["merge"] = merge
        target["status"] = "merged"
        target["completed_at"] = merge["completed_at"]
        _clear_merge_checkpoint(target)
        from agent_lab.evidence_sync import on_merge_approved

        on_merge_approved(
            folder,
            execution_id,
            commit_sha=str(merge.get("commit_sha") or "") or None,
        )
        _record_verify_after_merge(folder, target)
        snapshot_id = str(target.get("snapshot_id") or target.get("id") or "")
        if snapshot_id:
            delete_snapshot(folder, snapshot_id)


def _merge_conflict_execution(
    folder: Path,
    execution_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run = read_run_meta(folder)
    target = _find_execution(run, execution_id)
    if target is None:
        raise ValueError("execution not found")
    merge_raw = target.get("merge")
    merge: dict[str, Any] = merge_raw if isinstance(merge_raw, dict) else {}
    if target.get("status") != "merge_conflict" and merge.get("status") != "conflict":
        raise ValueError("execution is not in merge_conflict")
    if target.get("isolation_effective") != "worktree":
        raise ValueError("execution is not a worktree merge")
    return run, target
