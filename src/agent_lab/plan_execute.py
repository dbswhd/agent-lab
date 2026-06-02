"""Thin execute: plan action → Cursor edit → local snapshot diff → Human approve."""

from __future__ import annotations

import uuid
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.plan_actions import PlanAction, find_dry_run_action, parse_plan_action_sections
from agent_lab.plan_execute_git import resolve_action_git_context
from agent_lab.plan_execute_merge import MergeConflict, merge_exec_branch
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
from agent_lab.session_guidance import verify_execution_artifacts

EXECUTOR_ID = "cursor"
MAX_DIFF_CHARS = 120_000
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


def _cursor_execute_prompt(
    action: PlanAction,
    *,
    expected_paths: list[str] | None = None,
    verify: str | None = None,
) -> str:
    expected = ", ".join(expected_paths or action.expected_paths()) or action.where
    verify_line = verify if verify is not None else action.verify
    return f"""Agent Lab thin execute — implement exactly one plan action.

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


def _cursor_verify_follow_up(verify: str) -> str:
    return f"""Phase 2 — verify and fix (same Cursor session, keep using tools):
- Verification criterion from plan: {verify}
- Re-read changed files; run tests/commands/build steps named in the criterion.
- If anything fails, fix and re-check before you finish.
- End with a line: VERIFICATION: PASS — … or VERIFICATION: FAIL — …
- Then 3–5 lines summarizing files touched and what you verified."""


def _verify_follow_ups(verify: str) -> list[str]:
    text = (verify or "").strip()
    if not text or text in {"검증 기준 없음", "-", "—", "none", "N/A"}:
        return []
    return [_cursor_verify_follow_up(text)]


def _extract_draft_summary(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return ""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return "\n".join(lines[:8])


def run_dry_run(
    folder: Path,
    *,
    action_index: int,
    action_kind: str | None = None,
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from agent_lab.agents.cursor_agent import is_available, respond
    from agent_lab.plan_actions import PlanActionKind, parse_action_key

    if not is_available():
        raise RuntimeError("Cursor executor unavailable (CURSOR_API_KEY / cursor-sdk)")

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
    from agent_lab.room_objections import assert_execute_allowed

    assert_execute_allowed(run, action.index, action.kind)

    if _pending_execution(run):
        raise ValueError("finish or reject the pending execution first")

    base_cwd, effective_permissions, base_workspace_info = _preflight_execute_workspace(
        action, permissions
    )
    exec_id = _exec_id()
    action_key = f"{action.kind}:{action.index}"
    raw_source_paths = action.expected_paths()
    raw_verification_paths = action.verification_paths()
    raw_monitored_paths = action.monitored_paths()
    git_context = resolve_action_git_context(
        action_key=action_key,
        monitored_paths=raw_monitored_paths,
        cwd_hint=base_cwd,
    )
    exec_worktree: ExecWorktree | None = None
    worktree_commit_sha: str | None = None
    isolation_effective = git_context.isolation

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
            "executor": EXECUTOR_ID,
            "executor_label": "Cursor",
            "status": "blocked_isolation",
            "isolation_requested": git_context.isolation_source,
            "isolation_effective": git_context.isolation,
            "isolation_override": None,
            "action_git_context": git_context.to_dict(),
            "git_root": str(git_context.git_root) if git_context.git_root else None,
            "base_branch": git_context.base_branch,
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

    if git_context.isolation == "block":
        reason = git_context.block_reason or "isolation_blocked"
        message = f"execute isolation blocked: {reason}"
        _record_blocked(reason, message)
        raise WorktreeUnavailable(message, reason=reason)

    cwd = base_cwd
    workspace_info = base_workspace_info
    source_path_inputs = raw_source_paths
    verification_path_inputs = raw_verification_paths
    monitored_path_inputs = raw_monitored_paths
    if git_context.isolation == "worktree":
        if git_context.git_root is None:
            reason = "git_root_missing"
            message = "execute isolation blocked: git root missing"
            _record_blocked(reason, message)
            raise WorktreeUnavailable(message, reason=reason)
        try:
            exec_worktree = create_exec_worktree(
                folder,
                exec_id=exec_id,
                git_root=git_context.git_root,
                action_key=action_key,
                session_id=folder.name,
                base_branch=git_context.base_branch,
            )
        except WorktreeUnavailable as e:
            _record_blocked(e.reason, str(e))
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

    from agent_lab.room_hooks import PreExecuteBlocked, run_pre_execute_hooks

    pre_verify = run_pre_execute_hooks(
        run,
        action.to_dict(),
        session_folder=folder,
        session_id=folder.name,
    )
    if pre_verify.get("blocked"):
        if exec_worktree is not None:
            discard_exec_worktree(exec_worktree, folder, exec_id)
        raise PreExecuteBlocked(
            str(pre_verify.get("feedback") or "pre_execute hook blocked"),
            pre_verify=pre_verify,
        )

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

    try:
        agent_response = respond(
            system="You implement approved plan actions with minimal scope.",
            user=_cursor_execute_prompt(
                action,
                expected_paths=source_path_inputs,
                verify=verify_for_agent,
            ),
            permissions=effective_permissions,
            cwd=cwd,
            on_activity=_on_activity,
            follow_ups=_verify_follow_ups(verify_for_agent),
        )
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
        "executor": EXECUTOR_ID,
        "executor_label": "Cursor",
        "status": PENDING_STATUS,
        "isolation_requested": git_context.isolation_source,
        "isolation_effective": isolation_effective,
        "isolation_override": None,
        "action_git_context": git_context.to_dict(),
        "git_root": str(exec_worktree.git_root) if exec_worktree else (
            str(git_context.git_root) if git_context.git_root else None
        ),
        "base_branch": exec_worktree.base_branch if exec_worktree else git_context.base_branch,
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
    return execution


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
    if target.get("status") != PENDING_STATUS:
        raise ValueError("execution is not pending approval")

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
            else:
                merge.update(merge_result.to_dict())
                merge["completed_at"] = _now()
                target["merge"] = merge
                target["status"] = "merged"
                target["completed_at"] = merge["completed_at"]
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
