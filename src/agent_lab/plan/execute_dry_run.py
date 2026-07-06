from __future__ import annotations

"""Plan action dry-run — snapshot diff → pending approval (F9)."""

import subprocess
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunState

from agent_lab.adversarial_gate import adversarial_review
from agent_lab.plan.actions import PlanAction, find_dry_run_action, parse_plan_action_sections
from agent_lab.plan.execute_isolation import resolve_action_isolation
from agent_lab.plan.execute_paths import paths_relative_to_workspace, paths_under_workspace
from agent_lab.plan.execute_prompts import (
    _call_execute_agent,
    _cursor_execute_prompt,
    _extract_draft_summary,
)
from agent_lab.plan.execute_shared import (
    MAX_DIFF_CHARS,
    PENDING_STATUS,
    _commit_exec_worktree,
    _exec_id,
    _now,
    _preflight_execute_workspace,
    _rewrite_git_paths_in_text,
    _run_git,
    _worktree_hooks_setup,
    _worktree_paths,
    _workspace_info_for,
)
from agent_lab.plan.execute_snapshot import (
    build_diff,
    compute_touched_paths,
    create_snapshot,
    delete_snapshot,
    restore_snapshot,
)
from agent_lab.plan.execute_status import (
    _count_existed_files,
    _count_existed_in_paths,
    _needs_artifact_review,
    _paths_outside_expected,
    _pending_execution,
    _split_touched_paths,
)
from agent_lab.plan.execute_worktree import (
    ExecWorktree,
    WorktreeUnavailable,
    create_exec_worktree,
    discard_exec_worktree,
)
from agent_lab.runtime.adapters import (
    EXECUTE_AGENT_IDS,
    normalize_execute_agent as _normalize_execute_agent,
)

import agent_lab.plan.execute as plan_execute
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.session.guidance import verify_execution_artifacts
from agent_lab.workspace.roots import workspace_label


def _build_execution_record(
    *,
    exec_id: str,
    action: PlanAction,
    action_key: str,
    executor_id: str,
    isolation_decision: Any,
    isolation_effective: str,
    isolation_override: dict[str, Any] | None,
    exec_worktree: ExecWorktree | None,
    worktree_commit_sha: str | None,
    cwd: Path,
    workspace_info: dict[str, Any],
    verification_artifacts: dict[str, Any],
    raw_source_paths: list[str],
    raw_verification_paths: list[str],
    raw_monitored_paths: list[str],
    snapshot_paths: list[str],
    source_snapshot: list[str],
    artifact_snapshot: list[str],
    existed_before: int,
    source_touched: list[str],
    artifact_touched: list[str],
    empty_source_diff: bool,
    needs_artifact_review: bool,
    touched: list[str],
    outside: list[str],
    agent_response: str,
    activity_log: list[str],
    diff_stat: str,
    diff: str,
    started: str,
    worktree_hooks_block: dict[str, Any],
    supersedes_execution_id: str | None,
    revise_request: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble the execution record dict from dry-run results. Pure data, no I/O."""
    execution: dict[str, Any] = {
        "schema_version": 2,
        "id": exec_id,
        "action_id": action.action_id,
        "action_index": action.index,
        "action_kind": action.kind,
        "action_key": action_key,
        "action_what": action.what,
        "action_where": action.where,
        "action_verify": action.verify,
        "executor": executor_id,
        "executor_label": executor_id.title(),
        "status": PENDING_STATUS,
        "isolation_requested": isolation_decision.isolation_source,
        "isolation_source": isolation_decision.isolation_source,
        "isolation_effective": isolation_effective,
        "isolation_override": isolation_override,
        "isolation_override_by": "human" if isolation_override else None,
        "action_git_context": isolation_decision.to_dict(),
        "isolation_decision": isolation_decision.to_dict(),
        "git_root": str(exec_worktree.git_root)
        if exec_worktree
        else (str(isolation_decision.git_root) if isolation_decision.git_root else None),
        "base_branch": exec_worktree.base_branch if exec_worktree else isolation_decision.base_branch,
        "base_sha": exec_worktree.base_sha if exec_worktree else None,
        "exec_branch": exec_worktree.branch if exec_worktree else None,
        "exec_commit_sha": worktree_commit_sha,
        "worktree_path": str(exec_worktree.worktree_path) if exec_worktree else None,
        "snapshot_id": exec_id,
        "workspace_root": str(cwd),
        "workspace_label": workspace_label(cwd),
        "execute_workspace_info": workspace_info,
        "merge": {
            "status": "pending" if exec_worktree else None,
            "strategy": "merge" if exec_worktree else None,
            "commit_sha": None,
            "conflict_files": [],
            "attempted_at": None,
            "completed_at": None,
        },
        "verification_artifacts": verification_artifacts,
        "snapshotted_paths": raw_monitored_paths,
        "expected_paths": raw_source_paths,
        "verification_paths": raw_verification_paths,
        "monitored_paths": raw_monitored_paths,
        "snapshot_paths": snapshot_paths,
        "source_snapshot_paths": source_snapshot,
        "artifact_snapshot_paths": artifact_snapshot,
        "existed_before": existed_before,
        "source_touched_paths": source_touched,
        "artifact_touched_paths": artifact_touched,
        "empty_source_diff": empty_source_diff,
        "needs_artifact_review": needs_artifact_review,
        "touched_paths": touched,
        "paths_outside_expected": outside,
        "draft_summary": _extract_draft_summary(agent_response),
        "agent_response": (agent_response or "").strip(),
        "agent_log": activity_log,
        "diff_stat": diff_stat,
        "diff": diff,
        "started_at": started,
        "completed_at": None,
        "pre_verify": {},
    }
    if worktree_hooks_block:
        execution["worktree_hooks"] = worktree_hooks_block
    from agent_lab.diff_safety import diff_safety_enabled, scan_diff

    if diff_safety_enabled():
        execution["safety_scan"] = scan_diff(diff)
    if supersedes_execution_id:
        execution["revision_of"] = supersedes_execution_id
    if revise_request:
        execution["revise_requested"] = True
        execution["revise_note"] = str(revise_request.get("comment") or "")
        execution["revise_chunk_ref"] = revise_request.get("chunk_ref")
    adv = adversarial_review(
        action_what=action.what,
        action_verify=action.verify,
        diff=diff,
    )
    execution["adversarial_note"] = adv.get("note")
    execution["adversarial_source"] = adv.get("source")
    return execution


def _finalize_dry_run(
    folder: Path,
    *,
    execution: dict[str, Any],
    action: PlanAction,
    exec_id: str,
) -> None:
    """Append execution to run.json, mark tasks in-progress, emit events."""

    def _append(run: RunState) -> RunState:
        actions = list(run.get("actions") or [])
        if not any(a.get("action_id") == action.action_id for a in actions):
            actions.append(
                {
                    "action_id": action.action_id,
                    "index": action.index,
                    "kind": action.kind,
                    "what": action.what,
                    "where": action.where,
                    "verify": action.verify,
                    "refs": list(action.refs),
                }
            )
        executions = list(run.get("executions") or [])
        replaced = False
        for i, row in enumerate(executions):
            if row.get("id") == exec_id:
                executions[i] = execution
                replaced = True
                break
        if not replaced:
            executions.append(execution)
        run["actions"] = actions
        run["executions"] = executions
        return run

    patch_run_meta(folder, _append)

    def _mark_tasks(run: RunState) -> RunState:
        from agent_lab.room.tasks import mark_tasks_in_progress_for_execution

        mark_tasks_in_progress_for_execution(
            run,
            action_index=action.index,
            action_id=action.action_id,
            execution_id=exec_id,
        )
        return run

    patch_run_meta(folder, _mark_tasks)

    from agent_lab.evidence_sync import on_dry_run_recorded

    on_dry_run_recorded(folder, execution, action_index=action.index)

    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    dispatch(folder, RuntimeEvent.EXECUTE_DRY_RUN_COMPLETE, {"execution": execution})
    if str(execution.get("status") or "") == PENDING_STATUS:
        try:
            from agent_lab.gateway.notify_helpers import notify_merge_ready

            notify_merge_ready(folder, execution)
        except Exception:
            pass
        from agent_lab.auto_approve_gate import evaluate_auto_approve, mark_auto_approve_eligible

        _gate = evaluate_auto_approve(execution, read_run_meta(folder))
        if _gate.eligible:
            mark_auto_approve_eligible(execution, _gate)
            _exec_id = execution.get("id", "")

            def _stamp_auto(run: RunState) -> RunState:
                rows = list(run.get("executions") or [])
                for _i, _row in enumerate(rows):
                    if _row.get("id") == _exec_id:
                        rows[_i] = execution
                        break
                run["executions"] = rows
                return run

            patch_run_meta(folder, _stamp_auto)


def run_dry_run(
    folder: Path,
    *,
    action_index: int,
    action_kind: str | None = None,
    permissions: dict[str, Any] | None = None,
    isolation_override: dict[str, Any] | None = None,
    execution_id: str | None = None,
    executor: str | None = None,
    supersedes_execution_id: str | None = None,
    revise_request: dict[str, Any] | None = None,
    seed_commit_sha: str | None = None,
) -> dict[str, Any]:
    from agent_lab.plan.actions import PlanActionKind, parse_action_key

    executor_id = _normalize_execute_agent(executor)
    if not plan_execute._execute_agent_available(executor_id):
        raise RuntimeError(f"{executor_id.title()} executor unavailable")

    plan_path = folder / "plan.md"
    if not plan_path.is_file():
        raise FileNotFoundError("plan.md not found")

    plan_md = plan_path.read_text(encoding="utf-8")
    from agent_lab.plan.workflow import PlanWorkflowNotApproved, ensure_plan_workflow_approved

    try:
        ensure_plan_workflow_approved(folder)
    except PlanWorkflowNotApproved as exc:
        raise RuntimeError(f"plan workflow approval required (phase={exc.phase})") from exc
    from agent_lab.plan.pending import ensure_plan_snapshot_approved

    sections = parse_plan_action_sections(plan_md)
    recommended = sections.get("recommended")
    kind: PlanActionKind | None = None
    if action_kind:
        parsed = parse_action_key(action_kind)
        if parsed is None:
            if action_kind in ("now", "roadmap", "legacy"):
                kind = action_kind  # type: ignore[assignment]
            else:
                raise ValueError(f"invalid action_kind: {action_kind}")
        else:
            kind, action_index = parsed
    action = find_dry_run_action(plan_md, action_index, kind=kind)
    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    dispatch(
        folder,
        RuntimeEvent.EXECUTE_DRY_RUN_START,
        {"action_index": action_index},
    )
    if action is None:
        kind_hint = f" ({kind})" if kind else ""
        if recommended and recommended.get("index") != action_index:
            raise ValueError(
                f"action {action_index}{kind_hint} is not executable; dry-run only supports "
                "recommended or full 3-field roadmap items"
            )
        raise ValueError(f"no 3-field plan action with index {action_index}{kind_hint}")

    ensure_plan_snapshot_approved(folder, action, plan_md)

    run = read_run_meta(folder)
    from agent_lab.runtime.policy import PolicyEngine

    PolicyEngine.assert_execute_allowed(run, action.index, action.kind)

    pending = _pending_execution(run)
    if pending and pending.get("id") != execution_id and pending.get("id") != supersedes_execution_id:
        raise ValueError("finish or reject the pending execution first")

    base_cwd, effective_permissions, base_workspace_info = _preflight_execute_workspace(action, permissions)
    exec_id = execution_id or _exec_id()
    from agent_lab.mission.board import checkout_lane, sync_mission_board

    checkout_lane(
        folder,
        "execute",
        action_index=action.index,
        execution_id=exec_id,
    )

    def _sync_board(run: RunState) -> RunState:
        sync_mission_board(run, plan_md=plan_md)
        return run

    patch_run_meta(folder, _sync_board)
    action_key = f"{action.kind}:{action.index}"
    raw_source_paths = action.expected_paths()
    raw_verification_paths = action.verification_paths()
    raw_monitored_paths = action.monitored_paths()
    isolation_decision = resolve_action_isolation(
        action,
        permissions,
        base_cwd,
        override=isolation_override,
    )
    exec_worktree: ExecWorktree | None = None
    worktree_commit_sha: str | None = None
    isolation_effective = isolation_decision.isolation

    def _record_blocked(reason: str, message: str) -> None:
        blocked = {
            "schema_version": 2,
            "id": exec_id,
            "action_id": action.action_id,
            "action_index": action.index,
            "action_kind": action.kind,
            "action_key": action_key,
            "action_what": action.what,
            "action_where": action.where,
            "action_verify": action.verify,
            "executor": executor_id,
            "executor_label": executor_id.title(),
            "status": "blocked_isolation",
            "isolation_requested": isolation_decision.isolation_source,
            "isolation_source": isolation_decision.isolation_source,
            "isolation_effective": isolation_decision.isolation,
            "isolation_override": None,
            "action_git_context": isolation_decision.to_dict(),
            "isolation_decision": isolation_decision.to_dict(),
            "git_root": str(isolation_decision.git_root) if isolation_decision.git_root else None,
            "base_branch": isolation_decision.base_branch,
            "workspace_root": str(base_cwd),
            "workspace_label": workspace_label(base_cwd),
            "execute_workspace_info": base_workspace_info,
            "blocked_reason": reason,
            "blocked_message": message,
            "completed_at": _now(),
        }

        def _append_blocked(run: RunState) -> RunState:
            executions = list(run.get("executions") or [])
            executions.append(blocked)
            run["executions"] = executions
            return run

        patch_run_meta(folder, _append_blocked)

    if isolation_decision.isolation == "block":
        reason = isolation_decision.block_reason or "isolation_blocked"
        message = f"execute isolation blocked: {reason}"
        _record_blocked(reason, message)
        raise WorktreeUnavailable(message, reason=reason, execution_id=exec_id)

    cwd = base_cwd
    workspace_info = base_workspace_info
    source_path_inputs = raw_source_paths
    verification_path_inputs = raw_verification_paths
    monitored_path_inputs = raw_monitored_paths
    if isolation_decision.isolation == "worktree":
        if isolation_decision.git_root is None:
            reason = "git_root_missing"
            message = "execute isolation blocked: git root missing"
            _record_blocked(reason, message)
            raise WorktreeUnavailable(message, reason=reason, execution_id=exec_id)
        try:
            exec_worktree = create_exec_worktree(
                folder,
                exec_id=exec_id,
                git_root=isolation_decision.git_root,
                action_key=action_key,
                session_id=folder.name,
                base_branch=isolation_decision.base_branch,
            )
        except WorktreeUnavailable as e:
            _record_blocked(e.reason, str(e))
            e.execution_id = exec_id
            raise
        cwd = exec_worktree.worktree_path
        source_path_inputs = _worktree_paths(raw_source_paths, git_root=exec_worktree.git_root)
        verification_path_inputs = _worktree_paths(
            raw_verification_paths,
            git_root=exec_worktree.git_root,
        )
        monitored_path_inputs = _worktree_paths(
            raw_monitored_paths,
            git_root=exec_worktree.git_root,
        )
        workspace_info = _workspace_info_for(cwd, monitored_path_inputs)
        worktree_hooks_block = _worktree_hooks_setup(
            exec_worktree,
            folder=folder,
            exec_id=exec_id,
        )
    else:
        worktree_hooks_block = {}

    from agent_lab.room.hooks import PreExecuteBlocked
    from agent_lab.runtime.policy import PolicyEngine

    try:
        PolicyEngine.require_pre_execute(
            run,
            action.to_dict(),
            session_folder=folder,
            session_id=folder.name,
        )
    except PreExecuteBlocked:
        if exec_worktree is not None:
            discard_exec_worktree(exec_worktree, folder, exec_id)
        raise

    source_snapshot = paths_relative_to_workspace(cwd, source_path_inputs)
    artifact_snapshot = paths_relative_to_workspace(cwd, verification_path_inputs)
    snapshot_paths = paths_relative_to_workspace(cwd, monitored_path_inputs)
    manifest = create_snapshot(
        folder,
        exec_id=exec_id,
        cwd=cwd,
        expected_paths=snapshot_paths,
    )
    existed_before = _count_existed_files(manifest)
    source_existed = _count_existed_in_paths(manifest, source_snapshot)
    if raw_source_paths and source_existed == 0:
        if not paths_under_workspace(cwd, source_snapshot):
            delete_snapshot(folder, exec_id)
            raise ValueError(
                "none of the expected plan paths exist under the execute workspace; "
                f"checked {len(source_snapshot)} source path(s) in {cwd}"
            )
    if not raw_source_paths and snapshot_paths and existed_before == 0:
        pass
    if seed_commit_sha:
        if exec_worktree is None:
            delete_snapshot(folder, exec_id)
            raise ValueError("revision seed requires a worktree execution")
        try:
            _run_git(cwd, "cherry-pick", seed_commit_sha)
        except subprocess.CalledProcessError as e:
            _run_git(cwd, "cherry-pick", "--abort", check=False)
            delete_snapshot(folder, exec_id)
            discard_exec_worktree(exec_worktree, folder, exec_id)
            raise WorktreeUnavailable(
                "could not seed revision worktree from pending execution",
                reason="revision_seed_conflict",
                execution_id=exec_id,
            ) from e
    started = _now()
    activity_log: list[str] = []
    agent_response = ""
    verify_for_agent = action.verify
    if exec_worktree is not None:
        verify_for_agent = _rewrite_git_paths_in_text(
            action.verify,
            git_root=exec_worktree.git_root,
        )

    def _on_activity(label: str | None) -> None:
        if label and (not activity_log or activity_log[-1] != label):
            activity_log.append(label)

    from agent_lab.cursor.inbox_mcp import execute_inbox_mcp_enabled

    use_inbox_mcp = executor_id in EXECUTE_AGENT_IDS and execute_inbox_mcp_enabled()

    exec_permissions = dict(effective_permissions or {})
    if use_inbox_mcp:
        exec_permissions["_inbox_caller_agent"] = str(executor_id)
        exec_permissions["_inbox_policy_lane"] = "execute"

    from agent_lab.run.control import RoomRunCancelled, check_cancelled, run_guard

    with run_guard(
        session_id=folder.name,
        run_kind="execute",
        label=f"Execute action #{action.index}",
    ) as acquired:
        if not acquired:
            raise RuntimeError("a run is already in progress")
        try:
            check_cancelled()
            agent_response = _call_execute_agent(
                executor_id,
                user=_cursor_execute_prompt(
                    action,
                    expected_paths=source_path_inputs,
                    verify=verify_for_agent,
                    revise_request=revise_request,
                    inbox_mcp=use_inbox_mcp,
                ),
                permissions=exec_permissions,
                cwd=cwd,
                on_activity=_on_activity,
                verify=verify_for_agent,
                session_folder=folder,
                inbox_mcp=use_inbox_mcp,
                action=action,
                expected_paths=source_path_inputs,
                revise_request=revise_request,
            )
        except RoomRunCancelled:
            restore_snapshot(folder, exec_id=exec_id, cwd=cwd, manifest=manifest)
            delete_snapshot(folder, exec_id)
            if exec_worktree is not None:
                discard_exec_worktree(exec_worktree, folder, exec_id)
            from agent_lab.runtime.events import RuntimeEvent
            from agent_lab.runtime.runtime import dispatch

            dispatch(
                folder,
                RuntimeEvent.EXECUTE_DRY_RUN_CANCEL,
                {"reason": "dry_run_cancelled", "cleanup_executions": False},
            )
            raise
        except Exception as e:
            restore_snapshot(folder, exec_id=exec_id, cwd=cwd, manifest=manifest)
            delete_snapshot(folder, exec_id)
            if exec_worktree is not None:
                discard_exec_worktree(exec_worktree, folder, exec_id)
            raise RuntimeError(f"Cursor execute failed: {e}") from e

    touched = compute_touched_paths(
        folder,
        exec_id=exec_id,
        cwd=cwd,
        manifest=manifest,
        expected_paths=snapshot_paths,
    )
    source_touched, artifact_touched, empty_source_diff = _split_touched_paths(
        touched,
        source_snapshot=source_snapshot,
        artifact_snapshot=artifact_snapshot,
    )
    outside = _paths_outside_expected(touched, snapshot_paths, cwd=cwd)
    diff, diff_stat = build_diff(
        folder,
        exec_id=exec_id,
        cwd=cwd,
        manifest=manifest,
        touched_paths=touched,
    )
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[: MAX_DIFF_CHARS - 20] + "\n… (truncated)"

    needs_artifact_review = _needs_artifact_review(
        empty_source_diff=empty_source_diff,
        artifact_touched=artifact_touched,
        verification_paths=raw_verification_paths,
        draft_summary=_extract_draft_summary(agent_response),
    )
    verification_artifacts = verify_execution_artifacts(cwd, verification_path_inputs)

    if exec_worktree is not None:
        try:
            worktree_commit_sha = _commit_exec_worktree(
                worktree_path=exec_worktree.worktree_path,
                action=action,
                exec_id=exec_id,
            )
            if worktree_commit_sha is None and seed_commit_sha:
                worktree_commit_sha = _run_git(
                    exec_worktree.worktree_path,
                    "rev-parse",
                    "HEAD",
                ).stdout.strip()
        except Exception as e:
            restore_snapshot(folder, exec_id=exec_id, cwd=cwd, manifest=manifest)
            delete_snapshot(folder, exec_id)
            discard_exec_worktree(exec_worktree, folder, exec_id)
            raise RuntimeError(f"Cursor execute git commit failed: {e}") from e

    execution = _build_execution_record(
        exec_id=exec_id,
        action=action,
        action_key=action_key,
        executor_id=executor_id,
        isolation_decision=isolation_decision,
        isolation_effective=isolation_effective,
        isolation_override=isolation_override,
        exec_worktree=exec_worktree,
        worktree_commit_sha=worktree_commit_sha,
        cwd=cwd,
        workspace_info=workspace_info,
        verification_artifacts=verification_artifacts,
        raw_source_paths=raw_source_paths,
        raw_verification_paths=raw_verification_paths,
        raw_monitored_paths=raw_monitored_paths,
        snapshot_paths=snapshot_paths,
        source_snapshot=source_snapshot,
        artifact_snapshot=artifact_snapshot,
        existed_before=existed_before,
        source_touched=source_touched,
        artifact_touched=artifact_touched,
        empty_source_diff=empty_source_diff,
        needs_artifact_review=needs_artifact_review,
        touched=touched,
        outside=outside,
        agent_response=agent_response,
        activity_log=activity_log,
        diff_stat=diff_stat,
        diff=diff,
        started=started,
        worktree_hooks_block=worktree_hooks_block,
        supersedes_execution_id=supersedes_execution_id,
        revise_request=revise_request,
    )
    _finalize_dry_run(folder, execution=execution, action=action, exec_id=exec_id)
    run_after = read_run_meta(folder)
    for row in run_after.get("executions") or []:
        if isinstance(row, dict) and row.get("id") == exec_id:
            return row
    return execution
