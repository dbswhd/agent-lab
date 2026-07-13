from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Mapping, assert_never

from agent_lab.mission.decision_queue import (
    AnswerDecision,
    DecisionAnswered,
    DecisionEvent,
    DecisionExpired,
    ExpireDecision,
    HumanDecision,
    apply_decision_event,
    decide_decision,
)
from agent_lab.mission.journal import MissionJournal, PendingEvent
from agent_lab.mission.messages import JsonValue


class DecisionEventCodecError(ValueError):
    pass


class DecisionEventType(StrEnum):
    ANSWERED = "DecisionAnswered"
    EXPIRED = "DecisionExpired"


def _answer(payload: Mapping[str, JsonValue]) -> str:
    value = payload.get("answer")
    if not isinstance(value, str):
        raise DecisionEventCodecError("answer must be text")
    return value


def _identity(payload: Mapping[str, JsonValue], decision: HumanDecision) -> None:
    if payload.get("decision_id") != decision.id or payload.get("mission_id") != decision.mission_id:
        raise DecisionEventCodecError("decision identity does not match repository")


def _encode(event: DecisionEvent, decision: HumanDecision) -> PendingEvent:
    identity = {"decision_id": decision.id, "mission_id": decision.mission_id}
    match event:
        case DecisionAnswered(answer=answer):
            return PendingEvent(DecisionEventType.ANSWERED.value, {**identity, "answer": answer})
        case DecisionExpired():
            return PendingEvent(DecisionEventType.EXPIRED.value, identity)
        case _ as unreachable:
            assert_never(unreachable)


class DecisionRepository:
    def __init__(self, path: Path, decision: HumanDecision) -> None:
        self._journal = MissionJournal(path)
        self._initial = decision

    def load(self) -> HumanDecision:
        decision = self._initial
        for stored in self._journal.recover_tail():
            try:
                event_type = DecisionEventType(stored.event_type)
            except ValueError as exc:
                raise DecisionEventCodecError(f"unknown decision event: {stored.event_type}") from exc
            match event_type:
                case DecisionEventType.ANSWERED:
                    _identity(stored.payload, decision)
                    command: AnswerDecision | ExpireDecision = AnswerDecision(_answer(stored.payload))
                    decision = apply_decision_event(decision, decide_decision(decision, command)[0])
                case DecisionEventType.EXPIRED:
                    _identity(stored.payload, decision)
                    decision = apply_decision_event(decision, decide_decision(decision, ExpireDecision())[0])
                case _ as unreachable:
                    assert_never(unreachable)
        return decision

    def answer(self, command: AnswerDecision, *, expected_version: int | None = None) -> HumanDecision:
        return self._dispatch(command, expected_version=expected_version)

    def expire(self, *, expected_version: int | None = None) -> HumanDecision:
        return self._dispatch(ExpireDecision(), expected_version=expected_version)

    def _dispatch(self, command: AnswerDecision | ExpireDecision, *, expected_version: int | None) -> HumanDecision:
        current = self.load()
        events = decide_decision(current, command, expected_version=expected_version)
        self._journal.append(tuple(_encode(event, current) for event in events), expected_sequence=current.version)
        for event in events:
            current = apply_decision_event(current, event)
        return current
