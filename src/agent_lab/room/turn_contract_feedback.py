from __future__ import annotations

from collections.abc import Sequence
import hashlib
import os
from typing import TypedDict


class ContractOutcome(TypedDict, total=False):
    contract_id: str
    final_verdict: str | None
    repair_attempts: int
    escalated: bool
    task_kind: str | None
    risk: str | None
    execute_intent: bool


def _explore_rate() -> float:
    raw = (os.getenv("AGENT_LAB_FEEDBACK_EXPLORE_RATE") or "0").strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.0


def _context_match(row: ContractOutcome, *, task_kind: str, risk: str, execute_intent: bool) -> bool:
    return all(
        value is None or value == expected
        for value, expected in (
            (row.get("task_kind"), task_kind),
            (row.get("risk"), risk),
            (row.get("execute_intent"), execute_intent),
        )
    )


def contract_history_scores(
    history: Sequence[ContractOutcome],
    *,
    task_kind: str,
    risk: str,
    execute_intent: bool,
) -> tuple[dict[str, float], int, dict[str, int]]:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for row in history:
        if not _context_match(row, task_kind=task_kind, risk=risk, execute_intent=execute_intent):
            continue
        contract_id = str(row.get("contract_id") or "")
        if not contract_id:
            continue
        verdict = str(row.get("final_verdict") or "").lower()
        repair_attempts = int(row.get("repair_attempts") or 0)
        score = 1.0 if verdict == "pass" and repair_attempts == 0 else 0.5 if verdict == "pass" else -1.0
        if repair_attempts > 0:
            score -= 0.5
        if bool(row.get("escalated")):
            score -= 0.5
        totals[contract_id] = totals.get(contract_id, 0.0) + score
        counts[contract_id] = counts.get(contract_id, 0) + 1
    return (
        {contract_id: totals[contract_id] / counts[contract_id] for contract_id in totals},
        sum(counts.values()),
        counts,
    )


def derive_route_regrets(
    contract_id: str,
    *,
    escalated: bool,
    final_verdict: str | None,
    repair_attempts: int,
    rounds_used: int,
    execution_present: bool,
    clarify_no_delta: bool = False,
    fsm_no_action: bool = False,
    subset_escalated: bool = False,
) -> tuple[str, ...]:
    regrets: list[str] = []
    under_routed = contract_id == "quick_read" and (
        escalated or final_verdict == "fail" or repair_attempts > 0
    )
    if under_routed:
        regrets.append("under_routed")
    over_routed = contract_id in {"guarded_plan", "critical_review"} and not escalated and not execution_present and rounds_used <= 1
    if over_routed:
        regrets.append("over_routed_candidate")
    if clarify_no_delta:
        regrets.append("clarify_no_delta")
    if fsm_no_action:
        regrets.append("fsm_no_action")
    if subset_escalated:
        regrets.append("subset_escalated")
    return tuple(regrets)


def deterministic_explore_contract(
    candidates: Sequence[str],
    counts: dict[str, int],
    *,
    evidence: Sequence[str],
) -> str | None:
    rate = _explore_rate()
    if rate <= 0.0 or not candidates:
        return None
    stride = 1 if rate >= 1.0 else max(1, round(1.0 / rate))
    key = "|".join(evidence)
    offset = int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16) % stride
    if sum(counts.values()) % stride != offset:
        return None
    return min(candidates, key=lambda candidate: (counts.get(candidate, 0), candidate))
