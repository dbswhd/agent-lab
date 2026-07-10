from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import os
from typing import Final, Literal, TypedDict, cast

from agent_lab.run.state import RunStateLike
from agent_lab.room.turn_contract_feedback import (
    ContractOutcome,
    contract_history_scores,
    deterministic_explore_contract,
    derive_route_regrets,
)

__all__ = [
    "ContractOutcome",
    "ContractSnapshot",
    "RouteCandidate",
    "TurnContract",
    "TurnContractId",
    "TurnContractMode",
    "TurnObservation",
    "build_turn_contract",
    "derive_route_regrets",
    "deterministic_explore_contract",
    "observe_turn",
    "turn_contract_mode",
    "contract_runtime_controls",
]

RiskLevel = Literal["low", "medium", "high"]
Confidence = Literal["low", "medium", "high"]
TaskKind = Literal["read", "code", "review", "general"]
TurnContractMode = Literal["off", "shadow", "roles", "adaptive"]


class TurnContractId(StrEnum):
    QUICK_READ = "quick_read"
    STANDARD_COLLAB = "standard_collab"
    GUARDED_PLAN = "guarded_plan"
    CRITICAL_REVIEW = "critical_review"


class CandidateSnapshot(TypedDict):
    contract_id: str
    score: float
    evidence: list[str]
    rejected_by_safety: bool


class ContractSnapshot(TypedDict):
    contract_id: str
    source: str
    confidence: str
    safety_floor: str
    risk: str
    task_kind: str
    write_intent: bool
    execute_intent: bool
    ambiguity: str
    evidence: list[str]
    candidates: list[CandidateSnapshot]


@dataclass(frozen=True, slots=True)
class TurnObservation:
    task_kind: TaskKind
    write_intent: bool
    execute_intent: bool
    ambiguity: Confidence
    risk: RiskLevel
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    contract_id: TurnContractId
    score: float
    evidence: tuple[str, ...]
    rejected_by_safety: bool = False


@dataclass(frozen=True, slots=True)
class TurnContract:
    contract_id: TurnContractId
    source: Literal["bootstrap", "shadow", "history", "explore"]
    confidence: Confidence
    safety_floor: TurnContractId
    observation: TurnObservation
    candidates: tuple[RouteCandidate, ...]

    def to_snapshot(self) -> ContractSnapshot:
        return {
            "contract_id": self.contract_id.value,
            "source": self.source,
            "confidence": self.confidence,
            "safety_floor": self.safety_floor.value,
            "risk": self.observation.risk,
            "task_kind": self.observation.task_kind,
            "write_intent": self.observation.write_intent,
            "execute_intent": self.observation.execute_intent,
            "ambiguity": self.observation.ambiguity,
            "evidence": list(self.observation.evidence),
            "candidates": [
                {
                    "contract_id": candidate.contract_id.value,
                    "score": candidate.score,
                    "evidence": list(candidate.evidence),
                    "rejected_by_safety": candidate.rejected_by_safety,
                }
                for candidate in self.candidates
            ],
        }


_HIGH_RISK_MARKERS: Final[tuple[str, ...]] = (
    "결제",
    "금전",
    "거래",
    "payment",
    "financial",
    "finance",
    "security",
    "보안",
    "production",
    "프로덕션",
    "삭제",
    "drop table",
    "migration",
    "마이그레이션",
    "credential",
    "시크릿",
)
_EXECUTE_MARKERS: Final[tuple[str, ...]] = (
    "반영",
    "실제 코드",
    "실행",
    "merge",
    "worktree",
    "execute",
    "apply",
    "고쳐줘",
    "수정해줘",
)
_READ_MARKERS: Final[tuple[str, ...]] = (
    "검토",
    "분석",
    "설명",
    "확인",
    "review",
    "analyze",
    "explain",
    "어디에",
    "뭐야",
)
_QUICK_MARKERS: Final[tuple[str, ...]] = (
    "오타",
    "한 줄",
    "짧게",
    "단답",
    "확인만",
    "typo",
    "rename",
)


def _has_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def observe_turn(topic: str, run_meta: RunStateLike) -> TurnObservation:
    text = (topic or "").strip().lower()
    risk: RiskLevel = "high" if _has_marker(text, _HIGH_RISK_MARKERS) else "low"
    quick_intent = _has_marker(text, _QUICK_MARKERS)
    execute_intent = _has_marker(text, _EXECUTE_MARKERS) and not quick_intent
    write_intent = execute_intent or any(
        marker in text for marker in ("구현", "추가", "작성", "fix", "build", "patch")
    )
    read_intent = _has_marker(text, _READ_MARKERS)
    task_kind: TaskKind = "review" if read_intent else "code" if write_intent else "general"
    evidence: list[str] = []
    if risk == "high":
        evidence.append("high_risk_marker")
        if _has_marker(text, ("금전", "거래", "payment", "financial", "finance")):
            evidence.append("financial_domain")
    if execute_intent:
        evidence.append("execute_intent")
    if write_intent:
        evidence.append("write_intent")
    if quick_intent:
        evidence.append("quick_marker")
    if read_intent:
        evidence.append("review_intent")
    if isinstance(run_meta.get("plan_workflow"), dict):
        evidence.append("plan_workflow_state")
    ambiguity: Confidence = "low" if quick_intent or execute_intent else "medium"
    return TurnObservation(
        task_kind=task_kind,
        write_intent=write_intent,
        execute_intent=execute_intent,
        ambiguity=ambiguity,
        risk=risk,
        evidence=tuple(evidence),
    )


def turn_contract_mode() -> TurnContractMode:
    raw = os.getenv("AGENT_LAB_TURN_CONTRACT_MODE", "shadow").strip().lower()
    if raw in {"off", "shadow", "roles", "adaptive"}:
        return cast(TurnContractMode, raw)
    return "shadow"


def contract_runtime_controls(contract_id: str) -> tuple[int, int, bool]:
    if contract_id == TurnContractId.QUICK_READ.value:
        return 1, 1, False
    if contract_id in {TurnContractId.GUARDED_PLAN.value, TurnContractId.CRITICAL_REVIEW.value}:
        return 99, 2, True
    return 99, 1, False


def _candidate_score(contract_id: TurnContractId, observation: TurnObservation) -> float:
    score = {
        TurnContractId.QUICK_READ: 0.20,
        TurnContractId.STANDARD_COLLAB: 0.50,
        TurnContractId.GUARDED_PLAN: 0.35,
        TurnContractId.CRITICAL_REVIEW: 0.10,
    }[contract_id]
    if observation.risk == "high" and contract_id is TurnContractId.CRITICAL_REVIEW:
        score += 1.00
    if observation.execute_intent and contract_id is TurnContractId.GUARDED_PLAN:
        score += 1.00
    if observation.write_intent and contract_id is TurnContractId.STANDARD_COLLAB:
        score += 0.30
    if not observation.write_intent and contract_id is TurnContractId.QUICK_READ:
        score += 0.35
    if observation.task_kind == "review" and contract_id is TurnContractId.STANDARD_COLLAB:
        score += 0.20
    return score


def _safety_floor(observation: TurnObservation) -> TurnContractId:
    if observation.risk == "high":
        return TurnContractId.CRITICAL_REVIEW
    if observation.execute_intent:
        return TurnContractId.GUARDED_PLAN
    return TurnContractId.QUICK_READ


def _allowed(candidate: TurnContractId, floor: TurnContractId) -> bool:
    rank = {
        TurnContractId.QUICK_READ: 0,
        TurnContractId.STANDARD_COLLAB: 1,
        TurnContractId.GUARDED_PLAN: 2,
        TurnContractId.CRITICAL_REVIEW: 3,
    }
    return rank[candidate] >= rank[floor]


def build_turn_contract(
    observation: TurnObservation,
    *,
    history: list[ContractOutcome] | None = None,
) -> TurnContract:
    floor = _safety_floor(observation)
    ordered = tuple(TurnContractId)
    history_scores, history_count, history_counts = contract_history_scores(
        history or (),
        task_kind=observation.task_kind,
        risk=observation.risk,
        execute_intent=observation.execute_intent,
    )
    history_ready = history_count >= 10
    if history_ready:
        observation = replace(observation, evidence=observation.evidence + (f"history_n={history_count}",))
    candidates = tuple(
        RouteCandidate(
            contract_id=contract_id,
            score=_candidate_score(contract_id, observation)
            + (
                max(-0.5, min(0.5, history_scores.get(contract_id.value, 0.0) * 0.35))
                if history_ready
                else 0.0
            ),
            evidence=observation.evidence,
            rejected_by_safety=not _allowed(contract_id, floor),
        )
        for contract_id in ordered
    )
    eligible = tuple(candidate for candidate in candidates if not candidate.rejected_by_safety)
    explored = deterministic_explore_contract(
        [candidate.contract_id.value for candidate in eligible],
        history_counts,
        evidence=observation.evidence,
    ) if history_ready else None
    selected = (
        next(candidate for candidate in eligible if candidate.contract_id.value == explored)
        if explored
        else max(eligible, key=lambda candidate: (candidate.score, -ordered.index(candidate.contract_id)))
    )
    confidence: Confidence = "high" if observation.risk == "high" or observation.execute_intent else "low"
    return TurnContract(
        contract_id=selected.contract_id,
        source="explore" if explored else "history" if history_ready else "bootstrap",
        confidence=confidence,
        safety_floor=floor,
        observation=observation,
        candidates=candidates,
    )
