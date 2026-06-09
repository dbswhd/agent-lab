"""Thin execute: plan action → Cursor edit → local snapshot diff → Human approve."""

from __future__ import annotations

import uuid
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.adversarial_gate import adversarial_review
from agent_lab.plan_actions import PlanAction, find_dry_run_action, parse_plan_action_sections
from agent_lab.plan_execute_isolation import IsolationDecision, resolve_action_isolation
from agent_lab.plan_execute_merge import (
    MergeConflict,
    abort_exec_merge,
    confirm_exec_merge,
    merge_exec_branch,
    verify_after_merge,
)
from agent_lab.plan_execute_paths import paths_relative_to_workspace, paths_under_workspace
from agent_lab.plan_execute_snapshot import (
    build_diff,
    compute_touched_paths,
    create_snapshot,
    delete_snapshot,
    load_manifest,
    normalize_path,
    restore_snapshot,
)
from agent_lab.run_meta import patch_run_meta, read_run_meta
from agent_lab.workspace_roots import (
    execute_workspace_info,
    resolve_execute_workspace,
    workspace_label,
    workspace_path_info,
)
from agent_lab.plan_execute_worktree import (
    ExecWorktree,
    WorktreeUnavailable,
    create_exec_worktree,
    discard_exec_worktree,
)
from agent_lab.runtime.adapters import (
    DEFAULT_EXECUTE_AGENT as EXECUTOR_ID,
    EXECUTE_AGENT_IDS,
    execute_agent_available as _execute_agent_available,
    invoke_execute,
    invoke_repair,
    normalize_execute_agent as _normalize_execute_agent,
    pick_repair_agent as _repair_agent_id,
    verify_follow_ups,
)
from agent_lab.session_guidance import verify_execution_artifacts
MAX_DIFF_CHARS = 120_000
MAX_VERIFY_RETRIES = 2
PENDING_STATUS = "pending_approval"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exec_id() -> str:
    return f"exec-{uuid.uuid4().hex[:12]}"


def _count_existed_files(manifest: dict[str, Any]) -> int:
    files = manifest.get("files") or {}
    return sum(1 for entry in files.values() if entry.get("existed"))


def _count_existed_in_paths(manifest: dict[str, Any], paths: list[str]) -> int:
    files: dict[str, dict[str, Any]] = manifest.get("files") or {}
    count = 0
    for path in paths:
        if files.get(path, {}).get("existed"):
            count += 1
    return count


def _split_touched_paths(
    touched: list[str],
    *,
    source_snapshot: list[str],
    artifact_snapshot: list[str],
) -> tuple[list[str], list[str], bool]:
    source_set = set(source_snapshot)
    artifact_set = set(artifact_snapshot)
    source_touched = [path for path in touched if path in source_set]
    artifact_touched = [path for path in touched if path in artifact_set]
    return source_touched, artifact_touched, len(source_touched) == 0


def _needs_artifact_review(
    *,
    empty_source_diff: bool,
    artifact_touched: list[str],
    verification_paths: list[str],
    draft_summary: str,
) -> bool:
    if not empty_source_diff:
        return False
    if artifact_touched:
        return True
    return bool(verification_paths and draft_summary.strip())


def _approve_status(target: dict[str, Any]) -> str:
    if target.get("paths_outside_expected"):
        return "review_required"
    if _needs_artifact_review(
        empty_source_diff=bool(target.get("empty_source_diff")),
        artifact_touched=list(target.get("artifact_touched_paths") or []),
        verification_paths=list(target.get("verification_paths") or []),
        draft_summary=str(target.get("draft_summary") or ""),
    ):
        return "review_required"
    return "completed"


def execution_allows_task_complete(execution: dict[str, Any]) -> bool:
    """True when linked room tasks may be marked completed (mirrors _approve_status)."""
    status = str(execution.get("status") or "")
    if status in ("review_required", "pending_approval", "rejected", "failed"):
        return False
    oracle = execution.get("oracle")
    if isinstance(oracle, dict) and oracle.get("verdict") == "fail":
        return False
    if status == "completed":
        return True
    return _approve_status(execution) == "completed"


def _artifact_approve_block_reason(target: dict[str, Any]) -> str | None:
    """Block Human approve until PDF path + page count + artifacts are verified."""
    if not target.get("needs_artifact_review"):
        return None
    arts = target.get("verification_artifacts")
    if not isinstance(arts, dict):
        return "검증 산출물(PDF·break-report) 확인 후 승인하세요."
    pdf_path = arts.get("pdf_path")
    page_count = arts.get("pdf_page_count")
    break_report = arts.get("break_report")
    baseline_pages = None
    if isinstance(break_report, dict):
        baseline_pages = break_report.get("baselinePdfPageCount")
    if not pdf_path and not break_report:
        return "PDF 경로 또는 break-report.json 확인 후 승인하세요."
    if page_count is None and baseline_pages is None:
        return "PDF 페이지 수 확인 후 승인하세요."
    if not arts.get("ok"):
        return "검증 산출물이 불완전합니다 — PDF·break-report 확인 후 승인하세요."
    return None


def _paths_outside_expected(
    touched: list[str],
    expected: list[str],
    *,
    cwd: Path,
) -> list[str]:
    if not expected:
        return list(touched)
    expected_norm = {normalize_path(p, cwd=cwd) for p in expected}
    extras: list[str] = []
    for path in touched:
        norm = normalize_path(path, cwd=cwd)
        if any(
            norm == exp or norm.endswith(f"/{exp}") or exp.endswith(f"/{norm}")
            for exp in expected_norm
        ):
            continue
        if any(norm.startswith(exp.rstrip("/") + "/") for exp in expected_norm):
            continue
        extras.append(path)
    return extras


def _preflight_execute_workspace(
    action: PlanAction,
    permissions: dict[str, Any] | None,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Validate expected paths resolve under the chosen execute workspace."""
    monitored = action.monitored_paths()
    cwd, effective_permissions = resolve_execute_workspace(permissions, monitored)
    info = workspace_path_info(cwd, monitored)
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
    return workspace_path_info(cwd, raw_paths)


def _exec_worktree_from_execution(target: dict[str, Any]) -> ExecWorktree:
    missing = [
        key
        for key in ("git_root", "worktree_path", "exec_branch", "base_branch", "base_sha")
        if not target.get(key)
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


def _run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=check,
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


def _pending_execution(run: dict[str, Any]) -> dict[str, Any] | None:
    for row in reversed(run.get("executions") or []):
        if row.get("status") == PENDING_STATUS:
            return row
    return None


def _update_execution_row(
    folder: Path,
    *,
    execution_id: str,
    target: dict[str, Any],
) -> None:
    def _update(run: dict[str, Any]) -> dict[str, Any]:
        rows = list(run.get("executions") or [])
        for i, row in enumerate(rows):
            if row.get("id") == execution_id:
                rows[i] = target
                break
        run["executions"] = rows
        return run

    patch_run_meta(folder, _update)


def _execution_verify_action(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "what": target.get("action_what"),
        "where": target.get("action_where"),
        "verify": target.get("action_verify"),
    }


def _merged_verify_paths(target: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in (
        "source_touched_paths",
        "touched_paths",
        "expected_paths",
        "verification_paths",
        "monitored_paths",
    ):
        for raw in target.get(key) or []:
            path = str(raw)
            if path and path not in paths:
                paths.append(path)
    return paths


def _verify_workspace_root(target: dict[str, Any]) -> Path | None:
    raw = target.get("git_root") or target.get("workspace_root")
    return Path(str(raw)) if raw else None


def _notify_merge_conflict_mission(
    folder: Path,
    target: dict[str, Any],
) -> None:
    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    merge = target.get("merge") if isinstance(target.get("merge"), dict) else {}
    files = [str(f) for f in (merge.get("conflict_files") or []) if f]
    detail = ", ".join(files) if files else "unknown files"
    idx = target.get("action_index")
    dispatch(
        folder,
        RuntimeEvent.EXECUTE_STRUCTURAL_FAIL,
        {
            "reason": f"merge conflict: {detail}",
            "action_index": int(idx) if idx is not None else None,
        },
    )


def _record_verify_after_merge(
    folder: Path,
    target: dict[str, Any],
    *,
    verify_retries: int | None = None,
) -> dict[str, Any]:
    retries = int(
        verify_retries if verify_retries is not None else target.get("verify_retries") or 0
    )
    checked_at = _now()
    evidence = verify_after_merge(
        _execution_verify_action(target),
        _merged_verify_paths(target),
        session_folder=folder,
        workspace_root=_verify_workspace_root(target),
        verify_retries=retries,
    )
    evidence["checked_at"] = checked_at
    oracle = dict(evidence.get("oracle") or {})
    oracle["checked_at"] = checked_at
    evidence["oracle"] = oracle
    src = str(oracle.get("source") or "mock")
    evidence["source"] = "live_oracle" if src == "live" else "mock_oracle"
    target["verify_after_merge"] = evidence
    target["oracle"] = oracle
    target["verify_retries"] = retries
    target["reverify_endpoint"] = "/api/sessions/{session_id}/execute/reverify"
    history = list(target.get("verify_history") or [])
    history.append(
        {
            "attempt": retries,
            "checked_at": checked_at,
            "status": evidence.get("status"),
            "oracle": oracle,
        }
    )
    target["verify_history"] = history
    if str(target.get("status") or "") == "merged":
        from agent_lab.plan_execute_merge import archive_executed_diff

        exec_id = str(target.get("id") or "")
        if exec_id:
            archive_executed_diff(folder, execution_id=exec_id, execution=target)
    from agent_lab.runtime.runtime import dispatch_verify_result

    idx = int(target.get("action_index") or 0)
    verdict = str((oracle.get("verdict") or evidence.get("status") or "")).lower()
    reason = str(
        oracle.get("detail")
        or oracle.get("feedback")
        or oracle.get("reason")
        or ""
    )
    dispatch_verify_result(
        folder,
        action_index=idx,
        verdict=verdict,
        reason=reason,
        oracle=oracle,
    )
    return evidence


def _repair_prompt(target: dict[str, Any], *, attempt: int) -> str:
    oracle = target.get("oracle") if isinstance(target.get("oracle"), dict) else {}
    reason = str(oracle.get("detail") or "Oracle verification failed")
    paths = ", ".join(_merged_verify_paths(target)) or "(plan paths unavailable)"
    return f"""Layer 3 repair attempt {attempt}/{MAX_VERIFY_RETRIES}.

The previous merge completed, but the independent Oracle returned FAIL:
{reason}

Repair only the current plan action in this isolated worktree.
- 무엇을: {target.get("action_what") or target.get("action_key") or "plan action"}
- 어디서: {target.get("action_where") or paths}
- 검증: {target.get("action_verify") or "verify field missing"}
- 관련 경로: {paths}

Re-read the files, make the smallest required fix, and run the named verification.
End with `VERIFICATION: PASS — ...` or `VERIFICATION: FAIL — ...`."""


def _call_repair_agent(
    agent_id: str,
    *,
    target: dict[str, Any],
    worktree_path: Path,
    permissions: dict[str, Any] | None,
    attempt: int,
    session_folder: Path | None = None,
) -> str:
    prompt = _repair_prompt(target, attempt=attempt)
    if session_folder is not None:
        from agent_lab.runtime.context import enrich_execute_prompt
        from agent_lab.run_meta import read_run_meta
        from agent_lab.session_plugin_runtime import (
            enrich_execute_permissions,
            execute_plugin_prompt_addon,
        )

        permissions = enrich_execute_permissions(permissions, session_folder)
        prompt = execute_plugin_prompt_addon(prompt, session_folder, agent_id)
        prompt = enrich_execute_prompt(prompt, read_run_meta(session_folder))
    from agent_lab.runtime.adapters import RepairInvokeRequest

    effective = dict(permissions or {})
    effective["_discuss_cwd"] = str(worktree_path.resolve())
    return invoke_repair(
        agent_id,  # type: ignore[arg-type]
        RepairInvokeRequest(
            system="You repair a merged plan action after independent verification failed.",
            user=prompt,
            permissions=effective,
            cwd=worktree_path,
            verify_follow_ups=verify_follow_ups(str(target.get("action_verify") or "")),
        ),
    )


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


def _append_repair_history(
    target: dict[str, Any],
    repair: dict[str, Any],
) -> None:
    history = list(target.get("repair_history") or [])
    history.append(repair)
    target["repair_history"] = history
    target["last_repair"] = repair


def _mark_rejected_tasks(
    folder: Path,
    *,
    execution_id: str,
    target: dict[str, Any],
) -> None:
    def _revert_tasks(run: dict[str, Any]) -> dict[str, Any]:
        from agent_lab.room_tasks import revert_tasks_for_rejected_execution

        revert_tasks_for_rejected_execution(
            run,
            action_index=target.get("action_index"),
            action_id=target.get("action_id"),
            execution_id=execution_id,
        )
        return run

    patch_run_meta(folder, _revert_tasks)


def _mark_approved_effects(
    folder: Path,
    *,
    execution_id: str,
    target: dict[str, Any],
) -> dict[str, Any]:
    if execution_allows_task_complete(target):

        def _complete_linked_tasks(run: dict[str, Any]) -> dict[str, Any]:
            from agent_lab.room_tasks import complete_tasks_for_execution

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
    if target.get("status") in {"completed", "review_required"} or (
        target.get("status") == "merged" and execution_allows_task_complete(target)
    ):
        from agent_lab.plan_advance import advance_plan_after_approval

        plan_advance = advance_plan_after_approval(folder, target)
        if plan_advance.get("advanced"):
            completed_ts = target.get("completed_at") or _now()

            def _mark_plan(run: dict[str, Any]) -> dict[str, Any]:
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
    return plan_advance


def list_plan_actions(
    folder: Path,
    *,
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan_path = folder / "plan.md"
    if not plan_path.is_file():
        return {
            "recommended": None,
            "now": [],
            "roadmap": [],
            "actions": [],
        }
    plan_md = plan_path.read_text(encoding="utf-8")
    sections = parse_plan_action_sections(plan_md)
    recommended = sections["recommended"]
    if recommended is not None:
        monitored = recommended.get("monitored_paths") or recommended.get("expected_paths") or []
        recommended = dict(recommended)
        recommended["execute_workspace"] = execute_workspace_info(permissions, monitored)
    return {
        "recommended": recommended,
        "now": sections.get("now") or [],
        "roadmap": sections["roadmap"],
        "actions": sections["actions"],
    }


def _inbox_mcp_instructions(action: PlanAction) -> str:
    action_key = f"{action.kind}:{action.index}"
    return f"""
Human Inbox MCP (agent-lab-inbox) — mandatory for direction and GO:
- Before ANY file edits: plan-first phase. Draft a short execution plan from the approved plan.md.
- If blocked on direction, call `ask_human` with question + at least 2 options (never ask in prose).
- When the execution plan is ready, call `propose_build` with summary + action_ref="{action_key}" and wait for Human GO.
- Only after `propose_build` returns decision=go may you edit files (implement phase).
- If decision is defer or reject, stop without editing files.
- During implement, if blocked again, use `ask_human` only.
"""


def _cursor_plan_phase_prompt(
    action: PlanAction,
    *,
    expected_paths: list[str] | None = None,
    verify: str | None = None,
) -> str:
    expected = ", ".join(expected_paths or action.expected_paths()) or action.where
    verify_line = verify if verify is not None else action.verify
    inbox_block = _inbox_mcp_instructions(action)
    return f"""Agent Lab execute — plan-first phase ONLY (no file edits yet).
{inbox_block}
Plan action (from approved plan.md):
- 무엇을: {action.what}
- 어디서: {expected}
- 검증: {verify_line}

Phase 0 — plan-first:
- Read the repo as needed; draft a short execution plan for this action.
- If blocked on direction, call `ask_human` with at least 2 options (never ask in prose).
- When ready, call `propose_build` with summary + action_ref and STOP — do not edit files until Human GO."""


def _cursor_implement_phase_prompt(
    action: PlanAction,
    *,
    expected_paths: list[str] | None = None,
    verify: str | None = None,
    revise_request: dict[str, Any] | None = None,
) -> str:
    expected = ", ".join(expected_paths or action.expected_paths()) or action.where
    verify_line = verify if verify is not None else action.verify
    prompt = f"""Agent Lab execute — implement phase (Human GO received).

Phase 1 — implement (tools expected):
- Change only what is needed for this action.
- Prefer paths listed in "어디서": {expected}
- Do not refactor unrelated code.
- Do not commit; leave changes in the working tree.
- Read before edit; use tools like the IDE agent.
- During implement, if blocked again, use `ask_human` only.

Plan action:
- 무엇을: {action.what}
- 어디서: {expected}
- 검증: {verify_line}

When phase 1 edits are done, stop and wait — a phase 2 verification message follows in this same session."""
    if revise_request:
        chunk_ref = str(revise_request.get("chunk_ref") or "전체 diff")
        comment = str(revise_request.get("comment") or "").strip()
        selected_diff = str(revise_request.get("selected_diff") or "").strip()
        prompt += f"""

Human inline revise request:
- 선택 범위: {chunk_ref}
- 요청: {comment}

Revise the selected part without undoing correct parts of the plan action."""
        if selected_diff:
            prompt += f"""

Previous selected diff:
```diff
{selected_diff}
```"""
    return prompt


def _cursor_execute_prompt(
    action: PlanAction,
    *,
    expected_paths: list[str] | None = None,
    verify: str | None = None,
    revise_request: dict[str, Any] | None = None,
    inbox_mcp: bool = False,
) -> str:
    if inbox_mcp:
        return _cursor_plan_phase_prompt(
            action,
            expected_paths=expected_paths,
            verify=verify,
        )
    expected = ", ".join(expected_paths or action.expected_paths()) or action.where
    verify_line = verify if verify is not None else action.verify
    prompt = f"""Agent Lab thin execute — implement exactly one plan action.

Phase 1 — implement (tools expected):
- Change only what is needed for this action.
- Prefer paths listed in "어디서": {expected}
- Do not refactor unrelated code.
- Do not commit; leave changes in the working tree.
- Read before edit; use tools like the IDE agent.

Plan action:
- 무엇을: {action.what}
- 어디서: {expected}
- 검증: {verify_line}

When phase 1 edits are done, stop and wait — a phase 2 verification message follows in this same session."""
    if revise_request:
        chunk_ref = str(revise_request.get("chunk_ref") or "전체 diff")
        comment = str(revise_request.get("comment") or "").strip()
        selected_diff = str(revise_request.get("selected_diff") or "").strip()
        prompt += f"""

Human inline revise request:
- 선택 범위: {chunk_ref}
- 요청: {comment}

Revise the selected part without undoing correct parts of the plan action."""
        if selected_diff:
            prompt += f"""

Previous selected diff:
```diff
{selected_diff}
```"""
    return prompt


def _extract_draft_summary(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return ""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return "\n".join(lines[:8])


def _call_execute_agent(
    agent_id: str,
    *,
    user: str,
    permissions: dict[str, Any],
    cwd: Path,
    on_activity: Any,
    verify: str,
    session_folder: Path | None = None,
    inbox_mcp: bool = False,
    action: Any | None = None,
    expected_paths: list[str] | None = None,
    revise_request: dict[str, Any] | None = None,
) -> str:
    from agent_lab.runtime.adapters import ExecuteInvokeRequest

    system = "You implement approved plan actions with minimal scope."
    verify_ups = verify_follow_ups(verify)
    if session_folder is not None:
        from agent_lab.runtime.context import enrich_execute_prompt
        from agent_lab.run_meta import read_run_meta
        from agent_lab.session_plugin_runtime import (
            enrich_execute_permissions,
            execute_plugin_prompt_addon,
        )

        permissions = enrich_execute_permissions(permissions, session_folder)
        user = execute_plugin_prompt_addon(user, session_folder, agent_id)
        user = enrich_execute_prompt(user, read_run_meta(session_folder))

    req = ExecuteInvokeRequest(
        system=system,
        user=user,
        permissions=permissions,
        cwd=cwd,
        verify_follow_ups=verify_ups,
        on_activity=on_activity,
        session_folder=session_folder,
        inbox_mcp=inbox_mcp,
    )
    if inbox_mcp and session_folder is not None and action is not None:
        from agent_lab.human_inbox import execute_inbox_build_go

        req.plan_phase_user = _cursor_plan_phase_prompt(
            action,
            expected_paths=expected_paths,
            verify=verify,
        )
        req.implement_phase_user = _cursor_implement_phase_prompt(
            action,
            expected_paths=expected_paths,
            verify=verify,
            revise_request=revise_request,
        )
        req.inbox_gate = lambda: execute_inbox_build_go(session_folder)

    return invoke_execute(_normalize_execute_agent(agent_id), req)


def _selected_revision_diff(
    diff: str,
    *,
    chunk_ref: str | None,
    line_start: int | None,
    line_end: int | None,
    max_chars: int = 6000,
) -> str:
    lines = (diff or "").splitlines()
    selected: list[str] = []
    if line_start is not None:
        start = max(0, line_start - 1)
        end = max(start + 1, line_end or line_start)
        selected = lines[start:end]
    elif chunk_ref:
        for index, line in enumerate(lines):
            if line.strip() != chunk_ref.strip():
                continue
            selected.append(line)
            for following in lines[index + 1 :]:
                if following.startswith("@@") or following.startswith("diff --git "):
                    break
                selected.append(following)
            break
    else:
        selected = lines
    return "\n".join(selected)[:max_chars]


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
    from agent_lab.plan_actions import PlanActionKind, parse_action_key

    executor_id = _normalize_execute_agent(executor)
    if not _execute_agent_available(executor_id):
        raise RuntimeError(f"{executor_id.title()} executor unavailable")

    plan_path = folder / "plan.md"
    if not plan_path.is_file():
        raise FileNotFoundError("plan.md not found")

    plan_md = plan_path.read_text(encoding="utf-8")
    from agent_lab.plan_pending import ensure_plan_snapshot_approved

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
    if (
        pending
        and pending.get("id") != execution_id
        and pending.get("id") != supersedes_execution_id
    ):
        raise ValueError("finish or reject the pending execution first")

    base_cwd, effective_permissions, base_workspace_info = _preflight_execute_workspace(
        action, permissions
    )
    exec_id = execution_id or _exec_id()
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

        def _append_blocked(run: dict[str, Any]) -> dict[str, Any]:
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

    from agent_lab.room_hooks import PreExecuteBlocked
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

    from agent_lab.cursor_inbox_mcp import execute_inbox_mcp_enabled

    use_inbox_mcp = executor_id in EXECUTE_AGENT_IDS and execute_inbox_mcp_enabled()

    from agent_lab.run_control import RoomRunCancelled, check_cancelled

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
            permissions=effective_permissions,
            cwd=cwd,
            on_activity=_on_activity,
            verify=verify_for_agent,
            session_folder=folder,
            inbox_mcp=use_inbox_mcp,
            action=action,
            expected_paths=source_path_inputs,
            revise_request=revise_request,
        )
    except RoomRunCancelled as e:
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

    execution = {
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
        "git_root": str(exec_worktree.git_root) if exec_worktree else (
            str(isolation_decision.git_root) if isolation_decision.git_root else None
        ),
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
        "pre_verify": pre_verify,
    }
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

    def _append(run: dict[str, Any]) -> dict[str, Any]:
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

    def _mark_tasks(run: dict[str, Any]) -> dict[str, Any]:
        from agent_lab.room_tasks import mark_tasks_in_progress_for_execution

        mark_tasks_in_progress_for_execution(
            run,
            action_index=action.index,
            action_id=action.action_id,
            execution_id=exec_id,
        )
        return run

    patch_run_meta(folder, _mark_tasks)

    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    dispatch(folder, RuntimeEvent.EXECUTE_DRY_RUN_COMPLETE, {"execution": execution})
    return execution


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
    target = next(
        (row for row in run.get("executions") or [] if row.get("id") == execution_id),
        None,
    )
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
    return run_dry_run(
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
    executions = list(run.get("executions") or [])
    target = next((row for row in executions if row.get("id") == execution_id), None)
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
    replacement = run_dry_run(
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

    def _replace(run: dict[str, Any]) -> dict[str, Any]:
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


_CANCELLABLE_EXECUTION_STATUSES = frozenset(
    {PENDING_STATUS, "merge_conflict", "review_required", "pending"}
)


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
        target = next((row for row in executions if row.get("id") == execution_id), None)
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
) -> dict[str, Any]:
    vote_norm = vote.strip().lower()
    if vote_norm not in {"approve", "reject"}:
        raise ValueError("vote must be approve or reject")

    run = read_run_meta(folder)
    executions = list(run.get("executions") or [])
    target = next((row for row in executions if row.get("id") == execution_id), None)
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
    raw_expected_paths = list(
        target.get("expected_paths") or target.get("snapshotted_paths") or []
    )
    if stored_root:
        cwd = Path(stored_root)
    else:
        cwd, _ = resolve_execute_workspace(permissions, raw_expected_paths)
    snapshot_paths = list(target.get("snapshot_paths") or [])
    if not snapshot_paths:
        raw_monitored = list(
            target.get("monitored_paths")
            or target.get("snapshotted_paths")
            or target.get("expected_paths")
            or []
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
    completed = _now()

    if snapshot_id:
        try:
            manifest = load_manifest(folder, snapshot_id)
        except FileNotFoundError:
            manifest = None
    else:
        manifest = None

    if vote_norm == "reject":
        if manifest is not None:
            restore_snapshot(folder, exec_id=snapshot_id, cwd=cwd, manifest=manifest)
            delete_snapshot(folder, snapshot_id)
        if target.get("isolation_effective") == "worktree":
            discard_exec_worktree(_exec_worktree_from_execution(target), folder, execution_id)
        target["status"] = "rejected"
        target["completed_at"] = completed

        def _revert_tasks(run: dict[str, Any]) -> dict[str, Any]:
            from agent_lab.room_tasks import revert_tasks_for_rejected_execution

            revert_tasks_for_rejected_execution(
                run,
                action_index=target.get("action_index"),
                action_id=target.get("action_id"),
                execution_id=execution_id,
            )
            return run

        patch_run_meta(folder, _revert_tasks)
    else:
        block = _artifact_approve_block_reason(target)
        if block:
            raise ValueError(block)
        if retry_merge and target.get("isolation_effective") == "worktree":
            merge = dict(target.get("merge") or {})
            merge["attempted_at"] = completed
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
                _notify_merge_conflict_mission(folder, target)
            else:
                merge.update(merge_result.to_dict())
                merge["completed_at"] = _now()
                target["merge"] = merge
                target["status"] = "merged"
                target["completed_at"] = merge["completed_at"]
                _record_verify_after_merge(folder, target)
                snapshot_id = str(target.get("snapshot_id") or target.get("id") or "")
                if snapshot_id:
                    delete_snapshot(folder, snapshot_id)

            approval = {
                "id": f"appr-{uuid.uuid4().hex[:12]}",
                "execution_id": execution_id,
                "action_id": target.get("action_id"),
                "vote": vote_norm,
                "ts": completed,
                "by": "human",
            }

            def _update_retry(run: dict[str, Any]) -> dict[str, Any]:
                rows = list(run.get("executions") or [])
                for i, row in enumerate(rows):
                    if row.get("id") == execution_id:
                        rows[i] = target
                        break
                run["executions"] = rows
                approvals = list(run.get("execution_approvals") or [])
                approvals.append(approval)
                run["execution_approvals"] = approvals
                return run

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
            merge = dict(target.get("merge") or {})
            merge["attempted_at"] = completed
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
                _notify_merge_conflict_mission(folder, target)
            else:
                merge.update(merge_result.to_dict())
                merge["completed_at"] = _now()
                target["merge"] = merge
                target["status"] = "merged"
                target["completed_at"] = merge["completed_at"]
                _record_verify_after_merge(folder, target)
                if snapshot_id:
                    delete_snapshot(folder, snapshot_id)
        else:
            if snapshot_id:
                delete_snapshot(folder, snapshot_id)
            target["status"] = _approve_status(target)
            target["completed_at"] = completed

    approval = {
        "id": f"appr-{uuid.uuid4().hex[:12]}",
        "execution_id": execution_id,
        "action_id": target.get("action_id"),
        "vote": vote_norm,
        "ts": completed,
        "by": "human",
    }

    def _update(run: dict[str, Any]) -> dict[str, Any]:
        rows = list(run.get("executions") or [])
        for i, row in enumerate(rows):
            if row.get("id") == execution_id:
                rows[i] = target
                break
        run["executions"] = rows
        approvals = list(run.get("approvals") or [])
        approvals.append(approval)
        run["approvals"] = approvals
        return run

    patch_run_meta(folder, _update)

    if vote_norm == "approve" and execution_allows_task_complete(target):

        def _complete_linked_tasks(run: dict[str, Any]) -> dict[str, Any]:
            from agent_lab.room_tasks import complete_tasks_for_execution

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
        from agent_lab.plan_advance import advance_plan_after_approval

        plan_advance = advance_plan_after_approval(folder, target)
        if plan_advance.get("advanced"):
            completed_ts = target.get("completed_at") or completed

            def _mark_plan(run: dict[str, Any]) -> dict[str, Any]:
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


def _merge_conflict_execution(
    folder: Path,
    execution_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run = read_run_meta(folder)
    executions = list(run.get("executions") or [])
    target = next((row for row in executions if row.get("id") == execution_id), None)
    if target is None:
        raise ValueError("execution not found")
    merge = target.get("merge") if isinstance(target.get("merge"), dict) else {}
    if target.get("status") != "merge_conflict" and merge.get("status") != "conflict":
        raise ValueError("execution is not in merge_conflict")
    if target.get("isolation_effective") != "worktree":
        raise ValueError("execution is not a worktree merge")
    return run, target


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
    executions = list(run.get("executions") or [])
    target = next((row for row in executions if row.get("id") == execution_id), None)
    if target is None:
        raise ValueError("execution not found")
    if target.get("status") != "merged":
        raise ValueError("execution is not merged")
    oracle = target.get("oracle") if isinstance(target.get("oracle"), dict) else {}
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
    action_key = str(
        target.get("action_key")
        or f"{target.get('action_kind')}:{target.get('action_index')}"
    )
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

        merge = {
            "status": "pending",
            "strategy": "merge",
            "commit_sha": None,
            "conflict_files": [],
            "attempted_at": _now(),
            "completed_at": None,
        }
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
        evidence = _record_verify_after_merge(folder, target, verify_retries=attempt)
        repair["status"] = "merged"
        repair["merge"] = merge
        repair["completed_at"] = merge["completed_at"]
        repair["oracle_after"] = dict(evidence.get("oracle") or {})
        _append_repair_history(target, repair)
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
