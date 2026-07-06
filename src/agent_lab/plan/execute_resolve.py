from __future__ import annotations

"""Execution resolve — approve/reject, merge, repair (F9)."""

import uuid
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunState, RunStateLike

from agent_lab.plan.execute_merge import (
    MergeConflict,
    abort_exec_merge,
    confirm_exec_merge,
    merge_exec_branch,
)
from agent_lab.plan.execute_paths import paths_relative_to_workspace
from agent_lab.plan.execute_prompts import _extract_draft_summary, _selected_revision_diff
from agent_lab.plan.execute_shared import (
    MAX_VERIFY_RETRIES,
    PENDING_STATUS,
    _commit_repair_worktree,
    _do_worktree_merge,
    _exec_id,
    _exec_worktree_from_execution,
    _merge_commit_message,
    _merge_conflict_execution,
    _now,
    _resolve_reject,
    _resolve_snapshot_paths,
    _run_git,
    _worktree_hooks_verify_before_merge,
)
from agent_lab.plan.execute_snapshot import (
    compute_touched_paths,
    delete_snapshot,
    load_manifest,
    restore_snapshot,
)
from agent_lab.plan.execute_status import (
    _append_execution_approval,
    _approve_status,
    _artifact_approve_block_reason,
    _execution_approval_record,
    _finalize_auto_merge_meta,
    _find_execution,
    _mark_approved_effects,
    _mark_rejected_tasks,
    _needs_artifact_review,
    _split_touched_paths,
    _update_execution_row,
    execution_allows_task_complete,
)
from agent_lab.plan.execute_verify import (
    _append_repair_history,
    _arm_merge_checkpoint,
    _call_repair_agent,
    _clear_merge_checkpoint,
    _notify_merge_conflict_mission,
    _record_verify_after_merge,
)
from agent_lab.plan.execute_worktree import ExecWorktree, create_exec_worktree, discard_exec_worktree
from agent_lab.runtime.adapters import (
    DEFAULT_EXECUTE_AGENT as EXECUTOR_ID,
    pick_repair_agent as _repair_agent_id,
)
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.workspace.roots import resolve_execute_workspace

import agent_lab.plan.execute as plan_execute


_CANCELLABLE_EXECUTION_STATUSES = frozenset({PENDING_STATUS, "merge_conflict", "review_required", "pending"})


def run_isolation_override(
    folder: Path,
    *,
    execution_id: str,
    mode: str,
    confirmation: str,
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode_norm = mode.strip().lower()
    if mode_norm != "snapshot_override":
        raise ValueError("mode must be snapshot_override")
    confirm = confirmation.strip().lower()
    if "snapshot_override" not in confirm and "비격리" not in confirm:
        raise ValueError("confirmation must include snapshot_override or 비격리")

    run = read_run_meta(folder)
    target = _find_execution(run, execution_id)
    if target is None:
        raise ValueError("execution not found")
    if target.get("status") != "blocked_isolation":
        raise ValueError("execution is not blocked_isolation")
    action_index = target.get("action_index")
    action_kind = target.get("action_kind")
    if not isinstance(action_index, int):
        raise ValueError("blocked execution missing action_index")

    override = {
        "mode": "snapshot_override",
        "by": "human",
        "confirmation": confirmation,
        "requested_at": _now(),
        "blocked_reason": target.get("blocked_reason"),
    }
    return plan_execute.run_dry_run(
        folder,
        action_index=action_index,
        action_kind=str(action_kind or "now"),
        permissions=permissions,
        isolation_override=override,
        execution_id=execution_id,
    )


def revise_pending_execution(
    folder: Path,
    *,
    execution_id: str,
    comment: str,
    chunk_ref: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    permissions: dict[str, Any] | None = None,
    executor: str | None = None,
) -> dict[str, Any]:
    note = comment.strip()
    if not note:
        raise ValueError("revise comment is required")
    if line_start is not None and line_start < 1:
        raise ValueError("line_start must be at least 1")
    if line_end is not None and line_end < 1:
        raise ValueError("line_end must be at least 1")
    if line_start is not None and line_end is not None and line_end < line_start:
        raise ValueError("line_end must be greater than or equal to line_start")

    run = read_run_meta(folder)
    target = _find_execution(run, execution_id)
    if target is None:
        raise ValueError("pending execution not found")
    if target.get("status") != PENDING_STATUS:
        raise ValueError("execution is not pending approval")
    if target.get("isolation_effective") != "worktree":
        raise ValueError("inline revise requires a worktree execution")
    seed_commit_sha = str(target.get("exec_commit_sha") or "").strip()
    if not seed_commit_sha:
        raise ValueError("pending execution missing exec_commit_sha")
    action_index = target.get("action_index")
    if not isinstance(action_index, int):
        raise ValueError("pending execution missing action_index")

    requested_at = _now()
    revision_history = list(target.get("revision_history") or [])
    revision_entry: dict[str, Any] = {
        "attempt": len(revision_history) + 1,
        "requested_at": requested_at,
        "comment": note,
        "chunk_ref": chunk_ref,
        "line_start": line_start,
        "line_end": line_end,
        "previous_execution_id": execution_id,
        "previous_exec_commit_sha": target.get("exec_commit_sha"),
    }
    revise_request = {
        **revision_entry,
        "selected_diff": _selected_revision_diff(
            str(target.get("diff") or ""),
            chunk_ref=chunk_ref,
            line_start=line_start,
            line_end=line_end,
        ),
    }
    replacement = plan_execute.run_dry_run(
        folder,
        action_index=action_index,
        action_kind=str(target.get("action_kind") or "now"),
        permissions=permissions,
        execution_id=_exec_id(),
        executor=executor or str(target.get("executor") or EXECUTOR_ID),
        supersedes_execution_id=execution_id,
        revise_request=revise_request,
        seed_commit_sha=seed_commit_sha,
    )

    completed_at = _now()
    revision_entry["completed_at"] = completed_at
    revision_entry["replacement_execution_id"] = replacement["id"]
    revision_entry["status"] = "completed"
    replacement["revision_attempt"] = revision_entry["attempt"]
    replacement["revision_history"] = revision_history + [revision_entry]
    replacement["last_revision"] = revision_entry

    old_worktree = _exec_worktree_from_execution(target)
    discard_exec_worktree(old_worktree, folder, execution_id)
    snapshot_id = str(target.get("snapshot_id") or execution_id)
    if snapshot_id:
        delete_snapshot(folder, snapshot_id)

    target["status"] = "superseded"
    target["completed_at"] = completed_at
    target["revise_requested"] = True
    target["revise_note"] = note
    target["revise_chunk_ref"] = chunk_ref
    target["superseded_by"] = replacement["id"]
    target["revision_history"] = replacement["revision_history"]
    target["last_revision"] = revision_entry

    def _replace(run: RunState) -> RunState:
        rows = list(run.get("executions") or [])
        for index, row in enumerate(rows):
            if row.get("id") == execution_id:
                rows[index] = target
            elif row.get("id") == replacement["id"]:
                rows[index] = replacement
        run["executions"] = rows
        return run

    patch_run_meta(folder, _replace)
    return {
        "execution": replacement,
        "superseded_execution": target,
        "revision": revision_entry,
    }


_CANCELLABLE_EXECUTION_STATUSES = frozenset({PENDING_STATUS, "merge_conflict", "review_required", "pending"})


def cancel_open_execution(
    folder: Path,
    *,
    execution_id: str | None = None,
    reason: str = "user_cancel",
) -> dict[str, Any]:
    """Track D: reject open dry-run / merge-review execution and discard worktree."""
    run = read_run_meta(folder)
    executions = list(run.get("executions") or [])
    target: dict[str, Any] | None = None
    if execution_id:
        target = _find_execution(run, execution_id)
    else:
        for row in reversed(executions):
            if str(row.get("status") or "") in _CANCELLABLE_EXECUTION_STATUSES:
                target = row
                break
    if target is None:
        return {"skipped": True, "reason": "no_open_execution"}
    exec_id = str(target.get("id") or "")
    status = str(target.get("status") or "")
    if status not in _CANCELLABLE_EXECUTION_STATUSES:
        return {"skipped": True, "reason": "not_cancellable", "status": status}
    try:
        result = resolve_execution(folder, execution_id=exec_id, vote="reject")
    except ValueError as exc:
        return {"skipped": True, "reason": str(exc), "execution_id": exec_id}
    return {
        "status": "cancelled",
        "reason": reason,
        "execution_id": exec_id,
        "execution": result.get("execution"),
    }
def resolve_execution(
    folder: Path,
    *,
    execution_id: str,
    vote: str,
    permissions: dict[str, Any] | None = None,
    approved_by: str = "human",
    auto_merge_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    vote_norm = vote.strip().lower()
    if vote_norm not in {"approve", "reject"}:
        raise ValueError("vote must be approve or reject")

    run = read_run_meta(folder)
    target = _find_execution(run, execution_id)
    if target is None:
        raise ValueError("execution not found")
    status = target.get("status")
    allowed = {PENDING_STATUS, "merge_conflict"}
    if vote_norm == "reject":
        allowed = allowed | {"review_required"}
    if status not in allowed:
        raise ValueError("execution is not pending approval")
    retry_merge = status == "merge_conflict"

    stored_root = target.get("workspace_root")
    raw_expected_paths = list(target.get("expected_paths") or target.get("snapshotted_paths") or [])
    if stored_root:
        cwd = Path(stored_root)
    else:
        cwd, _ = resolve_execute_workspace(permissions, raw_expected_paths)
    snapshot_paths, source_snapshot, artifact_snapshot, snapshot_id = _resolve_snapshot_paths(target, cwd)
    completed = _now()

    if snapshot_id:
        try:
            manifest = load_manifest(folder, snapshot_id)
        except FileNotFoundError:
            manifest = None
    else:
        manifest = None

    if vote_norm == "reject":
        _resolve_reject(
            folder,
            target,
            manifest=manifest,
            snapshot_id=snapshot_id,
            cwd=cwd,
            execution_id=execution_id,
            completed=completed,
        )
    else:
        block = _artifact_approve_block_reason(target)
        if block:
            raise ValueError(block)
        _worktree_hooks_verify_before_merge(target, execution_id=execution_id)
        if retry_merge and target.get("isolation_effective") == "worktree":
            _do_worktree_merge(folder, execution_id, target, completed)
            if vote_norm == "approve" and approved_by == "auto":
                retry_auto_meta = _finalize_auto_merge_meta(
                    folder,
                    approved_by=approved_by,
                    target=target,
                    auto_merge_meta=auto_merge_meta,
                )
            else:
                retry_auto_meta = dict(auto_merge_meta or {})
            approval = _execution_approval_record(
                execution_id=execution_id,
                target=target,
                vote_norm=vote_norm,
                completed=completed,
                approved_by=approved_by,
                auto_merge_meta=retry_auto_meta,
            )

            def _update_retry(run: RunState) -> RunState:
                rows = list(run.get("executions") or [])
                for i, row in enumerate(rows):
                    if row.get("id") == execution_id:
                        rows[i] = target
                        break
                run["executions"] = rows
                return _append_execution_approval(run, approval)

            patch_run_meta(folder, _update_retry)
            return {
                "ok": True,
                "execution": target,
                "approval": approval,
            }

        if manifest is not None:
            touched = compute_touched_paths(
                folder,
                exec_id=snapshot_id,
                cwd=cwd,
                manifest=manifest,
                expected_paths=snapshot_paths,
            )
            source_touched, artifact_touched, empty_source_diff = _split_touched_paths(
                touched,
                source_snapshot=source_snapshot,
                artifact_snapshot=artifact_snapshot,
            )
            target["touched_paths"] = touched
            target["source_touched_paths"] = source_touched
            target["artifact_touched_paths"] = artifact_touched
            target["empty_source_diff"] = empty_source_diff
            target["needs_artifact_review"] = _needs_artifact_review(
                empty_source_diff=empty_source_diff,
                artifact_touched=artifact_touched,
                verification_paths=list(target.get("verification_paths") or []),
                draft_summary=str(target.get("draft_summary") or ""),
            )
        if target.get("isolation_effective") == "worktree":
            _do_worktree_merge(folder, execution_id, target, completed)
        else:
            if snapshot_id:
                delete_snapshot(folder, snapshot_id)
            target["status"] = _approve_status(target)
            target["completed_at"] = completed
            if vote_norm == "approve" and target.get("status") == "completed":
                from agent_lab.evidence_sync import on_merge_approved

                on_merge_approved(folder, execution_id, commit_sha=None)
                _record_verify_after_merge(folder, target)

    auto_meta: dict[str, Any] = (
        _finalize_auto_merge_meta(
            folder,
            approved_by=approved_by,
            target=target,
            auto_merge_meta=auto_merge_meta,
        )
        if vote_norm == "approve" and approved_by == "auto"
        else dict(auto_merge_meta or {})
    )
    approval = _execution_approval_record(
        execution_id=execution_id,
        target=target,
        vote_norm=vote_norm,
        completed=completed,
        approved_by=approved_by,
        auto_merge_meta=auto_meta,
    )

    def _update(run: RunState) -> RunState:
        rows = list(run.get("executions") or [])
        for i, row in enumerate(rows):
            if row.get("id") == execution_id:
                rows[i] = target
                break
        run["executions"] = rows
        return _append_execution_approval(run, approval)

    patch_run_meta(folder, _update)

    if vote_norm == "approve" and execution_allows_task_complete(target):

        def _complete_linked_tasks(run: RunState) -> RunState:
            from agent_lab.room.tasks import complete_tasks_for_execution

            complete_tasks_for_execution(
                run,
                action_index=target.get("action_index"),
                action_id=target.get("action_id"),
                execution_id=execution_id,
                execution=target,
            )
            return run

        patch_run_meta(folder, _complete_linked_tasks)

    plan_advance: dict[str, Any] = {"advanced": False}
    if vote_norm == "approve" and (
        target.get("status") in {"completed", "review_required"}
        or (target.get("status") == "merged" and execution_allows_task_complete(target))
    ):
        from agent_lab.plan.advance import advance_plan_after_approval

        plan_advance = advance_plan_after_approval(folder, target)
        if plan_advance.get("advanced"):
            completed_ts = target.get("completed_at") or completed

            def _mark_plan(run: RunState) -> RunState:
                run["last_plan_update"] = {
                    "trigger": "execute_advance",
                    "ts": completed_ts,
                    "completed_at": completed_ts,
                    "status": "completed",
                    "execution_id": execution_id,
                    "action_key": target.get("action_key"),
                    "promoted_action_key": plan_advance.get("promoted_action_key"),
                }
                return run

            patch_run_meta(folder, _mark_plan)

    return {"execution": target, "approval": approval, "plan_advance": plan_advance}

def abort_merge_execution(
    folder: Path,
    *,
    execution_id: str,
) -> dict[str, Any]:
    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    _run, target = _merge_conflict_execution(folder, execution_id)
    completed = _now()
    ew = _exec_worktree_from_execution(target)
    abort_exec_merge(ew, session_folder=folder, exec_id=execution_id)
    snapshot_id = str(target.get("snapshot_id") or target.get("id") or "")
    if snapshot_id:
        delete_snapshot(folder, snapshot_id)

    merge = dict(target.get("merge") or {})
    merge["status"] = "aborted"
    merge["completed_at"] = completed
    target["merge"] = merge
    target["status"] = "rejected"
    target["completed_at"] = completed
    _update_execution_row(folder, execution_id=execution_id, target=target)
    _mark_rejected_tasks(folder, execution_id=execution_id, target=target)
    dispatch(
        folder,
        RuntimeEvent.EXECUTE_MERGE_REJECTED,
        {"execution_id": execution_id},
    )
    return {"execution": target}


def confirm_merge_execution(
    folder: Path,
    *,
    execution_id: str,
) -> dict[str, Any]:
    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    _run, target = _merge_conflict_execution(folder, execution_id)
    dispatch(
        folder,
        RuntimeEvent.EXECUTE_MERGE_APPROVED,
        {"execution_id": execution_id},
    )
    completed = _now()
    ew = _exec_worktree_from_execution(target)
    _arm_merge_checkpoint(folder, execution_id=execution_id, target=target, op="confirm", worktree=ew)
    result = confirm_exec_merge(ew, session_folder=folder, exec_id=execution_id)
    snapshot_id = str(target.get("snapshot_id") or target.get("id") or "")
    if snapshot_id:
        delete_snapshot(folder, snapshot_id)

    merge = dict(target.get("merge") or {})
    merge.update(result.to_dict())
    merge["completed_at"] = completed
    target["merge"] = merge
    target["status"] = "merged"
    target["completed_at"] = completed
    _clear_merge_checkpoint(target)
    from agent_lab.evidence_sync import on_merge_approved

    on_merge_approved(
        folder,
        execution_id,
        commit_sha=str(merge.get("commit_sha") or "") or None,
    )
    _record_verify_after_merge(folder, target)
    _update_execution_row(folder, execution_id=execution_id, target=target)
    plan_advance = _mark_approved_effects(
        folder,
        execution_id=execution_id,
        target=target,
    )
    return {"execution": target, "plan_advance": plan_advance}


def reverify_merged_execution(
    folder: Path,
    *,
    execution_id: str,
    permissions: dict[str, Any] | None = None,
    executor: str | None = None,
) -> dict[str, Any]:
    run = read_run_meta(folder)
    target = _find_execution(run, execution_id)
    if target is None:
        raise ValueError("execution not found")
    if target.get("status") != "merged":
        raise ValueError("execution is not merged")
    oracle_raw = target.get("oracle")
    oracle: dict[str, Any] = oracle_raw if isinstance(oracle_raw, dict) else {}
    if oracle.get("verdict") != "fail":
        retries = int(target.get("verify_retries") or 0) + 1
        evidence = _record_verify_after_merge(folder, target, verify_retries=retries)
        _update_execution_row(folder, execution_id=execution_id, target=target)
        return {"execution": target, "verify_after_merge": evidence, "repair": None}

    retries = int(target.get("verify_retries") or 0)
    if retries >= MAX_VERIFY_RETRIES:
        raise ValueError(f"verify retry limit reached ({MAX_VERIFY_RETRIES})")
    if target.get("isolation_effective") != "worktree":
        raise ValueError("agent repair requires a worktree execution")
    git_root_raw = target.get("git_root")
    if not git_root_raw:
        raise ValueError("execution missing git_root")

    attempt = retries + 1
    started_at = _now()
    agent_id = _repair_agent_id(target, executor)
    repair_id = f"repair-{uuid.uuid4().hex[:12]}"
    action_key = str(target.get("action_key") or f"{target.get('action_kind')}:{target.get('action_index')}")
    ew = create_exec_worktree(
        folder,
        exec_id=execution_id,
        git_root=Path(str(git_root_raw)),
        action_key=f"{action_key}-repair-{attempt}",
        session_id=folder.name,
        base_branch=str(target.get("base_branch") or "") or None,
    )
    repair: dict[str, Any] = {
        "id": repair_id,
        "attempt": attempt,
        "agent": agent_id,
        "status": "running",
        "started_at": started_at,
        "oracle_before": dict(oracle),
        **ew.to_dict(),
    }
    try:
        response = _call_repair_agent(
            agent_id,
            target=target,
            worktree_path=ew.worktree_path,
            permissions=permissions,
            attempt=attempt,
            session_folder=folder,
        )
        repair_commit = _commit_repair_worktree(
            ew.worktree_path,
            target=target,
            attempt=attempt,
        )
        repair["agent_response"] = _extract_draft_summary(response)
        repair["exec_commit_sha"] = repair_commit
        if repair_commit is None:
            discard_exec_worktree(ew, folder, execution_id)
            evidence = _record_verify_after_merge(folder, target, verify_retries=attempt)
            repair["status"] = "no_changes"
            repair["completed_at"] = _now()
            repair["oracle_after"] = dict(evidence.get("oracle") or {})
            _append_repair_history(target, repair)
            from agent_lab.evidence_sync import on_repair_recorded

            on_repair_recorded(folder, execution_id, attempt=attempt, detail="no_changes")
            _update_execution_row(folder, execution_id=execution_id, target=target)
            plan_advance = _mark_approved_effects(
                folder,
                execution_id=execution_id,
                target=target,
            )
            return {
                "execution": target,
                "verify_after_merge": evidence,
                "repair": repair,
                "plan_advance": plan_advance,
            }

        merge: dict[str, Any] = {
            "status": "pending",
            "strategy": "merge",
            "commit_sha": None,
            "conflict_files": [],
            "attempted_at": _now(),
            "completed_at": None,
        }
        _arm_merge_checkpoint(
            folder,
            execution_id=execution_id,
            target=target,
            op="repair_merge",
            worktree=ew,
            exec_commit_sha=repair_commit,
        )
        try:
            merge_result = merge_exec_branch(
                ew,
                session_folder=folder,
                exec_id=execution_id,
                message=f"agent-lab: repair {action_key} attempt {attempt}",
            )
        except MergeConflict as exc:
            merge["status"] = "conflict"
            merge["conflict_files"] = exc.conflict_files
            merge["completed_at"] = _now()
            target.update(ew.to_dict())
            target["exec_commit_sha"] = repair_commit
            target["merge"] = merge
            target["status"] = "merge_conflict"
            target["verify_retries"] = attempt
            _clear_merge_checkpoint(target)
            repair["status"] = "merge_conflict"
            repair["merge"] = merge
            repair["completed_at"] = merge["completed_at"]
            _append_repair_history(target, repair)
            _update_execution_row(folder, execution_id=execution_id, target=target)
            _notify_merge_conflict_mission(folder, target)
            return {
                "execution": target,
                "verify_after_merge": target.get("verify_after_merge"),
                "repair": repair,
            }

        merge.update(merge_result.to_dict())
        merge["completed_at"] = _now()
        target.update(ew.to_dict())
        target["exec_commit_sha"] = repair_commit
        target["merge"] = merge
        target["status"] = "merged"
        target["completed_at"] = merge["completed_at"]
        _clear_merge_checkpoint(target)
        evidence = _record_verify_after_merge(folder, target, verify_retries=attempt)
        repair["status"] = "merged"
        repair["merge"] = merge
        repair["completed_at"] = merge["completed_at"]
        repair["oracle_after"] = dict(evidence.get("oracle") or {})
        _append_repair_history(target, repair)
        from agent_lab.evidence_sync import on_repair_recorded

        on_repair_recorded(folder, execution_id, attempt=attempt)
    except Exception:
        if ew.worktree_path.exists():
            discard_exec_worktree(ew, folder, execution_id)
        raise

    _update_execution_row(folder, execution_id=execution_id, target=target)
    plan_advance = _mark_approved_effects(
        folder,
        execution_id=execution_id,
        target=target,
    )
    return {
        "execution": target,
        "verify_after_merge": evidence,
        "repair": repair,
        "plan_advance": plan_advance,
    }
