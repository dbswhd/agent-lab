"""Trust-gated Auto-approval gate (P1-4).

Decides whether a pending execution is eligible for auto-approval based on:
  1. AGENT_LAB_AUTO_APPROVE_THRESHOLD (low | medium | high — disabled if unset)
  2. Diff risk level (diff_risk.assess_diff_risk)
  3. Trust budget remaining

If eligible, stamps auto_approve_at (deadline) onto the execution so the API
layer can trigger resolve_execution(approved_by="auto") when the timer elapses.
Setting AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC=0 enables immediate auto-approval.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from agent_lab.time_utils import utc_now
from agent_lab.diff_risk import RiskLevel, assess_diff_risk
from agent_lab.run.state import RunStateLike

_TIER_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


def auto_approve_threshold() -> RiskLevel | None:
    """Max risk level eligible for auto-approval. None = feature disabled."""
    raw = (os.getenv("AGENT_LAB_AUTO_APPROVE_THRESHOLD") or "").strip().lower()
    if raw in ("low", "medium", "high"):
        return raw  # type: ignore[return-value]
    return None


def auto_approve_timeout_sec() -> int:
    """Seconds of human override window before auto-approval triggers. Default 30."""
    try:
        return max(0, int(os.getenv("AGENT_LAB_AUTO_APPROVE_TIMEOUT_SEC") or "30"))
    except (TypeError, ValueError):
        return 30



@dataclass
class AutoApproveDecision:
    eligible: bool
    reason: str
    risk_level: RiskLevel | None
    risk_reasons: list[str] = field(default_factory=list)
    threshold: RiskLevel | None = None
    timeout_sec: int = 30


def evaluate_auto_approve(
    execution: dict[str, Any],
    run_meta: RunStateLike | None,
) -> AutoApproveDecision:
    """Return whether a pending execution can be auto-approved."""
    from agent_lab.autonomy_ladder import effective_auto_approve_threshold, resolve_display_autonomy_level

    timeout = auto_approve_timeout_sec()
    threshold = effective_auto_approve_threshold(run_meta)

    if threshold is None:
        return AutoApproveDecision(
            eligible=False,
            reason="auto_approve_disabled",
            risk_level=None,
            threshold=None,
            timeout_sec=timeout,
        )

    display = resolve_display_autonomy_level(run_meta)
    if display == "L0":
        return AutoApproveDecision(
            eligible=False,
            reason="autonomy_below_l1",
            risk_level=None,
            threshold=threshold,
            timeout_sec=timeout,
        )

    if execution.get("status") != "pending_approval":
        return AutoApproveDecision(
            eligible=False,
            reason="not_pending_approval",
            risk_level=None,
            threshold=threshold,
            timeout_sec=timeout,
        )

    risk_level, risk_reasons = assess_diff_risk(execution)

    if _TIER_RANK[risk_level] > _TIER_RANK[threshold]:
        return AutoApproveDecision(
            eligible=False,
            reason=f"risk_exceeds_threshold:{risk_level}>{threshold}",
            risk_level=risk_level,
            risk_reasons=risk_reasons,
            threshold=threshold,
            timeout_sec=timeout,
        )

    from agent_lab.trust_budget import get_trust_budget

    budget = get_trust_budget(run_meta)
    total = int(budget.get("auto_merge_total") or 0)
    remaining = int(budget.get("auto_merge_remaining") or 0)
    if total > 0 and remaining <= 0:
        return AutoApproveDecision(
            eligible=False,
            reason="trust_budget_exhausted",
            risk_level=risk_level,
            risk_reasons=risk_reasons,
            threshold=threshold,
            timeout_sec=timeout,
        )

    return AutoApproveDecision(
        eligible=True,
        reason="eligible",
        risk_level=risk_level,
        risk_reasons=risk_reasons,
        threshold=threshold,
        timeout_sec=timeout,
    )


def mark_auto_approve_eligible(
    execution: dict[str, Any],
    decision: AutoApproveDecision,
) -> None:
    """Stamp auto-approve metadata onto the execution dict (in-place)."""
    deadline = (utc_now() + timedelta(seconds=decision.timeout_sec)).replace(microsecond=0).isoformat()
    execution["auto_approve_eligible"] = True
    execution["auto_approve_threshold"] = decision.threshold
    execution["auto_approve_risk_level"] = decision.risk_level
    execution["auto_approve_risk_reasons"] = decision.risk_reasons
    execution["auto_approve_at"] = deadline
    execution["auto_approve_timeout_sec"] = decision.timeout_sec


def auto_approve_deadline_passed(execution: dict[str, Any]) -> bool:
    """True if the auto-approve window has elapsed for this execution."""
    if not execution.get("auto_approve_eligible"):
        return False
    raw = str(execution.get("auto_approve_at") or "")
    if not raw:
        return False
    try:
        deadline = datetime.fromisoformat(raw)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return utc_now() >= deadline
    except ValueError:
        return False


def try_auto_approve(folder: Any, execution_id: str) -> dict[str, Any] | None:
    """Attempt auto-approval if deadline has passed. Returns resolve result or None."""
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(folder)
    target = next(
        (r for r in (run.get("executions") or []) if r.get("id") == execution_id),
        None,
    )
    if target is None:
        return None
    if not auto_approve_deadline_passed(target):
        return None
    if target.get("status") != "pending_approval":
        return None

    from agent_lab.plan.execute import resolve_execution

    meta = {
        "risk_level": target.get("auto_approve_risk_level"),
        "risk_reasons": target.get("auto_approve_risk_reasons"),
        "threshold": target.get("auto_approve_threshold"),
        "timeout_sec": target.get("auto_approve_timeout_sec"),
    }
    return resolve_execution(
        folder,
        execution_id=execution_id,
        vote="approve",
        approved_by="auto",
        auto_merge_meta=meta,
    )
