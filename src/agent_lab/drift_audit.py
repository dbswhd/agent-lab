"""C2 — L3 drift audit: periodic plan-vs-execution coverage check.

See docs/N10-USER-LOOP-WISDOM-DRAFT.md §4-C2. An autonomous mission (L3,
NORTH-STAR §1 Layer 2) can run many turns unattended; a plan action can fall
out of scope (context summarization, a re-drafted plan.md, an agent losing
track) with nobody watching to notice — the 2026-07-06 usage audit found this
exact failure mode in a real multi-day session ("극초반 거는 구현이 안 됐네").

This module snapshots the plan.md action list once per autonomous segment and,
every ``AGENT_LAB_DRIFT_AUDIT_INTERVAL`` human turns, diffs it against
``executions[]``. Any baseline action with no matching execution is proposed
back to the human via Inbox — this is pure comparison against existing state
(``executions``, ``mission_loop``), not a new learning loop.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunStateLike

DEFAULT_DRIFT_AUDIT_INTERVAL = 10


def _flag_on(name: str, *, default: str = "1") -> bool:
    raw = (os.getenv(name) or default).strip().lower()
    return raw not in ("0", "false", "no", "off")


def drift_audit_enabled() -> bool:
    return _flag_on("AGENT_LAB_DRIFT_AUDIT")


def drift_audit_interval() -> int:
    raw = (os.getenv("AGENT_LAB_DRIFT_AUDIT_INTERVAL") or str(DEFAULT_DRIFT_AUDIT_INTERVAL)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_DRIFT_AUDIT_INTERVAL


def snapshot_drift_baseline(folder: Path, plan_md: str, human_turn: int) -> None:
    """Freeze the current plan.md action list as the drift-audit baseline (fail-open)."""
    try:
        from agent_lab.plan.actions import parse_plan_actions
        from agent_lab.run.meta import patch_run_meta

        actions = parse_plan_actions(plan_md or "")
        baseline = {
            "human_turn": human_turn,
            "actions": [{"index": a.index, "what": a.what, "kind": a.kind} for a in actions],
        }

        def _patch(run: dict[str, Any]) -> dict[str, Any]:
            run["drift_baseline"] = baseline
            return run

        patch_run_meta(folder, _patch)
    except Exception:  # fail-open: baseline snapshot must never block mission start
        import logging

        logging.getLogger(__name__).warning("snapshot_drift_baseline failed for %s", folder, exc_info=True)


def _executed_action_indices(run_meta: RunStateLike) -> set[int]:
    out: set[int] = set()
    for execution in run_meta.get("executions") or []:
        if not isinstance(execution, dict):
            continue
        idx = execution.get("action_index")
        if isinstance(idx, int):
            out.add(idx)
    return out


def uncovered_actions(run_meta: RunStateLike) -> list[dict[str, Any]]:
    """Baseline actions with no matching execution row — pure comparison, no I/O."""
    baseline = run_meta.get("drift_baseline")
    if not isinstance(baseline, dict):
        return []
    executed = _executed_action_indices(run_meta)
    return [a for a in (baseline.get("actions") or []) if isinstance(a, dict) and a.get("index") not in executed]


def _pending_drift_escalation(run_meta: RunStateLike, baseline_turn: int) -> bool:
    for item in run_meta.get("human_inbox") or []:
        if not isinstance(item, dict) or item.get("status") != "pending":
            continue
        if item.get("kind") != "drift_audit":
            continue
        refs = list(item.get("refs") or [])
        if refs[:1] == [str(baseline_turn)]:
            return True
    return False


def _escalate_drift(folder: Path, baseline_turn: int, missing: list[dict[str, Any]]) -> dict[str, Any] | None:
    from agent_lab.human_inbox import create_inbox_item

    lines = [f"{a.get('index')}. {a.get('what')}" for a in missing[:5]]
    more = f" 외 {len(missing) - 5}건" if len(missing) > 5 else ""
    summary = "; ".join(lines) + more
    return create_inbox_item(
        folder,
        kind="drift_audit",
        source="drift_audit",
        prompt=f"초기 plan 대비 미완료 항목 {len(missing)}건이 남아 있습니다: {summary}",
        summary=summary,
        options=[
            {"id": "reground", "label": "재접지(계속 진행)"},
            {"id": "split", "label": "미션 분할 검토"},
        ],
        refs=[str(baseline_turn), *[str(a.get("index")) for a in missing]],
    )


def maybe_run_drift_audit(folder: Path, human_turn: int) -> dict[str, Any] | None:
    """Periodic L3 drift check at turn close (fail-open, flag-gated, mission-scoped)."""
    try:
        from agent_lab.mission.loop import get_mission_loop
        from agent_lab.run.meta import read_run_meta

        if not drift_audit_enabled():
            return None
        run_meta = read_run_meta(folder)
        ml = get_mission_loop(run_meta)
        if not ml.get("autonomous_segment", {}).get("active"):
            return None
        baseline = run_meta.get("drift_baseline")
        if not isinstance(baseline, dict):
            return None
        baseline_turn = int(baseline.get("human_turn") or 0)
        elapsed = human_turn - baseline_turn
        if elapsed <= 0 or elapsed % drift_audit_interval() != 0:
            return None
        missing = uncovered_actions(run_meta)
        if not missing:
            return None
        if _pending_drift_escalation(run_meta, baseline_turn):
            return None
        return _escalate_drift(folder, baseline_turn, missing)
    except Exception:  # fail-open: drift audit must never block turn completion
        import logging

        logging.getLogger(__name__).warning("maybe_run_drift_audit failed for %s", folder, exc_info=True)
        return None


def handle_drift_audit_inbox_resolve(
    folder: Path,
    item: dict[str, Any],
    *,
    selected: list[str] | None,
    status: str,
) -> None:
    """Side-effect helper when inbox drift_audit is resolved (mirrors skill_drafts).

    "재접지" re-snapshots the baseline from the CURRENT plan.md at the CURRENT
    turn, restarting the N-turn audit window. "미션 분할 검토" is informational
    only — automated mission splitting is out of scope (Human decides how).
    """
    if item.get("kind") != "drift_audit":
        return
    if status in ("rejected", "superseded"):
        return
    choice = (selected or [""])[0].strip().lower()
    if choice != "reground":
        return

    from agent_lab.room.messages import _human_turn_count
    from agent_lab.room.session_persist import _session_context, load_session_messages

    plan_md, _ = _session_context(folder)
    human_turn = _human_turn_count(load_session_messages(folder))
    snapshot_drift_baseline(folder, plan_md, human_turn)


__all__ = [
    "DEFAULT_DRIFT_AUDIT_INTERVAL",
    "drift_audit_enabled",
    "drift_audit_interval",
    "snapshot_drift_baseline",
    "uncovered_actions",
    "maybe_run_drift_audit",
    "handle_drift_audit_inbox_resolve",
]
