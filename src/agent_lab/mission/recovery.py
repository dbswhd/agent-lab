from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never


class SideEffectState(StrEnum):
    NOT_STARTED = "not_started"
    STARTED = "started"
    COMMITTED = "committed"
    FAILED = "failed"


class RecoveryAction(StrEnum):
    REQUEUE = "requeue"
    RECONCILE = "reconcile"
    COMPLETE = "complete"
    RETRY = "retry"


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    activity_id: str
    action: RecoveryAction
    reason: str


def decide_recovery(activity_id: str, state: SideEffectState) -> RecoveryDecision:
    match state:
        case SideEffectState.NOT_STARTED:
            return RecoveryDecision(activity_id, RecoveryAction.REQUEUE, "lease expired before side effect started")
        case SideEffectState.STARTED:
            return RecoveryDecision(activity_id, RecoveryAction.RECONCILE, "side effect may have committed")
        case SideEffectState.COMMITTED:
            return RecoveryDecision(activity_id, RecoveryAction.COMPLETE, "side effect commit is durable")
        case SideEffectState.FAILED:
            return RecoveryDecision(activity_id, RecoveryAction.RETRY, "side effect failed before terminal commit")
        case _ as unreachable:
            assert_never(unreachable)
