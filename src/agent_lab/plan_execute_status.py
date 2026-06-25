"""Execution approval/status helpers: diff classification, approve-status, task effects, approval records."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from agent_lab.plan_execute_snapshot import (
    normalize_path,
)
from agent_lab.run_meta import patch_run_meta


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
        if any(norm == exp or norm.endswith(f"/{exp}") or exp.endswith(f"/{norm}") for exp in expected_norm):
            continue
        if any(norm.startswith(exp.rstrip("/") + "/") for exp in expected_norm):
            continue
        extras.append(path)
    return extras


def _pending_execution(run: dict[str, Any]) -> dict[str, Any] | None:
    from agent_lab.plan_execute import PENDING_STATUS

    for row in reversed(run.get("executions") or []):
        if row.get("status") == PENDING_STATUS:
            return row
    return None


def _find_execution(run: dict[str, Any], execution_id: str) -> dict[str, Any] | None:
    return next(
        (row for row in run.get("executions") or [] if row.get("id") == execution_id),
        None,
    )


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
    from agent_lab.plan_execute import _now

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


def _execution_approval_record(
    *,
    execution_id: str,
    target: dict[str, Any],
    vote_norm: str,
    completed: str,
    approved_by: str = "human",
    auto_merge_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    approval: dict[str, Any] = {
        "id": f"appr-{uuid.uuid4().hex[:12]}",
        "execution_id": execution_id,
        "action_id": target.get("action_id"),
        "vote": vote_norm,
        "ts": completed,
        "by": approved_by,
    }
    if auto_merge_meta:
        approval["auto_merge"] = True
        approval.update(auto_merge_meta)
    return approval


def _append_execution_approval(run: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    for key in ("approvals", "execution_approvals"):
        rows = list(run.get(key) or [])
        rows.append(approval)
        run[key] = rows
    return run


def _finalize_auto_merge_meta(
    folder: Path,
    *,
    approved_by: str,
    target: dict[str, Any],
    auto_merge_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    meta = dict(auto_merge_meta or {})
    if approved_by != "auto":
        return meta
    if target.get("status") not in {"merged", "completed"}:
        raise ValueError("auto_merge did not complete")
    from agent_lab.trust_budget import consume_auto_merge_budget

    before, after = consume_auto_merge_budget(folder)
    meta["budget_before"] = before
    meta["budget_after"] = after
    return meta
