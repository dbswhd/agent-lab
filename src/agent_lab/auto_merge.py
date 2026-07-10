"""Auto-merge eligibility — trust budget + classifier + merge checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.gate_scope import get_gate_profile
from agent_lab.merge_checks import build_merge_checks
from agent_lab.merge_classifier import public_classifier_preview
from agent_lab.run.meta import read_run_meta
from agent_lab.trust_budget import get_trust_budget


from agent_lab.plan.execution_status_scopes import find_open_merge_pending_execution


def _pending_execution(run: dict[str, Any]) -> dict[str, Any] | None:
    return find_open_merge_pending_execution(run)


def evaluate_auto_merge_eligibility(
    folder: Path,
    *,
    execution_id: str | None = None,
) -> dict[str, Any]:
    run = read_run_meta(folder)
    profile = get_gate_profile(run)
    budget = get_trust_budget(run)
    pending = _pending_execution(run)
    if execution_id:
        pending = next(
            (row for row in (run.get("executions") or []) if isinstance(row, dict) and row.get("id") == execution_id),
            None,
        )
    classifier_preview = public_classifier_preview(pending)
    classifier = classifier_preview.get("classifier")
    allowed = {str(x) for x in (budget.get("classifier_allow") or [])}

    checks = build_merge_checks(run, pending_execution=pending)
    remaining = int(budget.get("auto_merge_remaining") or 0)

    result: dict[str, Any] = {
        "eligible": False,
        "gate_profile": profile,
        "classifier": classifier,
        "classifier_preview": classifier_preview,
        "trust_budget": {
            "auto_merge_remaining": remaining,
            "auto_merge_total": int(budget.get("auto_merge_total") or 0),
            "classifier_allow": sorted(allowed),
        },
        "merge_checks_ok": not checks.get("merge_disabled"),
        "merge_disabled_reason": checks.get("merge_disabled_reason"),
        "pending_execution_id": pending.get("id") if pending else None,
        "reason": None,
    }

    if profile != "assistant":
        result["reason"] = "dev_profile_requires_human_merge"
        return result
    if pending is None:
        result["reason"] = "no_pending_execution"
        return result
    if checks.get("merge_disabled"):
        result["reason"] = checks.get("merge_disabled_reason") or "merge_checks_failed"
        return result
    if remaining <= 0:
        result["reason"] = "trust_budget_exhausted"
        return result
    if not classifier:
        result["reason"] = "classifier_denied"
        return result
    if classifier not in allowed:
        result["reason"] = "classifier_not_allowed"
        return result

    result["eligible"] = True
    result["reason"] = None
    return result


def resolve_auto_merge(folder: Path, *, execution_id: str) -> dict[str, Any]:
    """Auto-merge when eligible; consumes trust budget on successful merge."""
    from agent_lab.plan.execute import resolve_execution

    elig = evaluate_auto_merge_eligibility(folder, execution_id=execution_id)
    if not elig.get("eligible"):
        raise ValueError(str(elig.get("reason") or "auto_merge not eligible"))
    result = resolve_execution(
        folder,
        execution_id=execution_id,
        vote="approve",
        approved_by="auto",
        auto_merge_meta={"classifier": elig.get("classifier")},
    )
    approval = result.get("approval") or {}
    result["auto_merge"] = {
        "eligible": True,
        "classifier": elig.get("classifier"),
        "budget_before": approval.get("budget_before"),
        "budget_after": approval.get("budget_after"),
    }
    return result
