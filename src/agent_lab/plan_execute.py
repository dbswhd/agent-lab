"""Thin execute: plan action → Cursor edit → local snapshot diff → Human approve."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.plan_actions import PlanAction, find_dry_run_action, parse_plan_action_sections
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
from agent_lab.workspace_roots import primary_workspace

EXECUTOR_ID = "cursor"
MAX_DIFF_CHARS = 120_000
PENDING_STATUS = "pending_approval"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exec_id() -> str:
    return f"exec-{uuid.uuid4().hex[:12]}"


def _paths_outside_expected(
    touched: list[str],
    expected: list[str],
) -> list[str]:
    if not expected:
        return list(touched)
    expected_norm = {normalize_path(p) for p in expected}
    extras: list[str] = []
    for path in touched:
        norm = normalize_path(path)
        if any(
            norm == exp or norm.endswith(f"/{exp}") or exp.endswith(f"/{norm}")
            for exp in expected_norm
        ):
            continue
        if any(norm.startswith(exp.rstrip("/") + "/") for exp in expected_norm):
            continue
        extras.append(path)
    return extras


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
            "roadmap": [],
            "actions": [],
        }
    plan_md = plan_path.read_text(encoding="utf-8")
    sections = parse_plan_action_sections(plan_md)
    return {
        "recommended": sections["recommended"],
        "roadmap": sections["roadmap"],
        "actions": sections["actions"],
    }


def _cursor_execute_prompt(action: PlanAction) -> str:
    expected = ", ".join(action.expected_paths()) or action.where
    return f"""Agent Lab thin execute — implement exactly one plan action.

Rules:
- Change only what is needed for this action.
- Prefer paths listed in "어디서": {expected}
- Do not refactor unrelated code.
- Do not commit; leave changes in the working tree.

Plan action:
- 무엇을: {action.what}
- 어디서: {action.where}
- 검증: {action.verify}

When finished, reply with 3–5 lines summarizing what you changed and which files you touched."""


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
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from agent_lab.agents.cursor_agent import is_available, respond

    if not is_available():
        raise RuntimeError("Cursor executor unavailable (CURSOR_API_KEY / cursor-sdk)")

    plan_path = folder / "plan.md"
    if not plan_path.is_file():
        raise FileNotFoundError("plan.md not found")

    plan_md = plan_path.read_text(encoding="utf-8")
    sections = parse_plan_action_sections(plan_md)
    recommended = sections.get("recommended")
    action = find_dry_run_action(plan_md, action_index)
    if action is None:
        if recommended and recommended.get("index") != action_index:
            raise ValueError(
                f"action {action_index} is not executable; dry-run only supports "
                "recommended or full 3-field roadmap items"
            )
        raise ValueError(f"no 3-field plan action with index {action_index}")

    run = read_run_meta(folder)
    if _pending_execution(run):
        raise ValueError("finish or reject the pending execution first")

    cwd = primary_workspace(permissions)
    exec_id = _exec_id()
    expected_paths = action.expected_paths()
    manifest = create_snapshot(
        folder,
        exec_id=exec_id,
        cwd=cwd,
        expected_paths=expected_paths,
    )
    started = _now()
    try:
        summary = respond(
            system="You implement approved plan actions with minimal scope.",
            user=_cursor_execute_prompt(action),
            permissions=permissions,
        )
    except Exception as e:
        restore_snapshot(folder, exec_id=exec_id, cwd=cwd, manifest=manifest)
        delete_snapshot(folder, exec_id)
        raise RuntimeError(f"Cursor execute failed: {e}") from e

    touched = compute_touched_paths(
        folder,
        exec_id=exec_id,
        cwd=cwd,
        manifest=manifest,
        expected_paths=expected_paths,
    )
    outside = _paths_outside_expected(touched, expected_paths)
    diff, diff_stat = build_diff(
        folder,
        exec_id=exec_id,
        cwd=cwd,
        manifest=manifest,
        touched_paths=touched,
    )
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[: MAX_DIFF_CHARS - 20] + "\n… (truncated)"

    execution = {
        "id": exec_id,
        "action_id": action.action_id,
        "action_index": action.index,
        "executor": EXECUTOR_ID,
        "status": PENDING_STATUS,
        "snapshot_id": exec_id,
        "snapshotted_paths": expected_paths,
        "expected_paths": expected_paths,
        "touched_paths": touched,
        "paths_outside_expected": outside,
        "draft_summary": _extract_draft_summary(summary),
        "diff_stat": diff_stat,
        "diff": diff,
        "started_at": started,
        "completed_at": None,
    }

    def _append(run: dict[str, Any]) -> dict[str, Any]:
        actions = list(run.get("actions") or [])
        if not any(a.get("action_id") == action.action_id for a in actions):
            actions.append(
                {
                    "action_id": action.action_id,
                    "index": action.index,
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

    cwd = primary_workspace(permissions)
    snapshot_id = str(target.get("snapshot_id") or target.get("id") or "")
    expected_paths = list(target.get("expected_paths") or target.get("snapshotted_paths") or [])
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
        target["status"] = "rejected"
        target["completed_at"] = completed
    else:
        if manifest is not None:
            target["touched_paths"] = compute_touched_paths(
                folder,
                exec_id=snapshot_id,
                cwd=cwd,
                manifest=manifest,
                expected_paths=expected_paths,
            )
            delete_snapshot(folder, snapshot_id)
        outside = list(target.get("paths_outside_expected") or [])
        target["status"] = "review_required" if outside else "completed"
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
    return {"execution": target, "approval": approval}
