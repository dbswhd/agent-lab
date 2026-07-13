from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import assert_never


class DecisionStatus(StrEnum):
    PENDING = "PENDING"
    ANSWERED = "ANSWERED"
    EXPIRED = "EXPIRED"


class DecisionTransitionError(Exception):
    def __init__(self, command: str, status: DecisionStatus, reason: str) -> None:
        self.command = command
        self.status = status
        self.reason = reason
        super().__init__(command, status, reason)

    def __str__(self) -> str:
        return f"{self.command} rejected in {self.status}: {self.reason}"


@dataclass(frozen=True, slots=True)
class HumanDecision:
    id: str
    mission_id: str
    question: str
    kind: str
    status: DecisionStatus = DecisionStatus.PENDING
    version: int = 0
    answer: str | None = None


@dataclass(frozen=True, slots=True)
class AnswerDecision:
    answer: str


@dataclass(frozen=True, slots=True)
class ExpireDecision:
    pass


DecisionCommand = AnswerDecision | ExpireDecision


@dataclass(frozen=True, slots=True)
class DecisionAnswered:
    answer: str


@dataclass(frozen=True, slots=True)
class DecisionExpired:
    pass


DecisionEvent = DecisionAnswered | DecisionExpired


def new_decision(decision_id: str, mission_id: str, question: str, kind: str) -> HumanDecision:
    return HumanDecision(decision_id, mission_id, question, kind)


def _reject(decision: HumanDecision, command: DecisionCommand, reason: str) -> DecisionTransitionError:
    return DecisionTransitionError(type(command).__name__, decision.status, reason)


def decide_decision(
    decision: HumanDecision,
    command: DecisionCommand,
    *,
    expected_version: int | None = None,
) -> tuple[DecisionEvent, ...]:
    if expected_version is not None and decision.version != expected_version:
        raise _reject(decision, command, f"expected version {expected_version}, got {decision.version}")
    if decision.status is not DecisionStatus.PENDING:
        raise _reject(decision, command, "decision is already terminal")
    match command:
        case AnswerDecision(answer=answer):
            if not answer.strip():
                raise _reject(decision, command, "answer is required")
            return (DecisionAnswered(answer),)
        case ExpireDecision():
            return (DecisionExpired(),)
        case _ as unreachable:
            assert_never(unreachable)


def apply_decision_event(decision: HumanDecision, event: DecisionEvent) -> HumanDecision:
    match event:
        case DecisionAnswered(answer=answer):
            return replace(decision, status=DecisionStatus.ANSWERED, version=decision.version + 1, answer=answer)
        case DecisionExpired():
            return replace(decision, status=DecisionStatus.EXPIRED, version=decision.version + 1)
        case _ as unreachable:
            assert_never(unreachable)
