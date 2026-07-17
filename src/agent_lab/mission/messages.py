from __future__ import annotations

"""Prototype envelope for a generic message bus — superseded by domain-specific
durable implementations for command/event/human_decision (see
docs/redesign-2026-07/08-collaboration-messaging.md §13 D6/D10). Not deleted:
JsonValue is still reused elsewhere and the ActorKind/MessageKind vocabulary
stays useful as reference, but nothing new should be built on this envelope.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, TypeAlias, assert_never

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


class ActorKind(StrEnum):
    HUMAN = "human"
    CONDUCTOR = "conductor"
    AGENT = "agent"
    TOOL = "tool"
    SYSTEM = "system"
    EXTENSION = "extension"


class MessageKind(StrEnum):
    COMMAND = "command"
    EVENT = "event"
    WORK_REQUEST = "work_request"
    PROGRESS = "progress"
    HUMAN_DECISION = "human_decision"
    ARTIFACT_REF = "artifact_ref"


class DeliveryGuarantee(StrEnum):
    AT_LEAST_ONCE = "at_least_once"
    BEST_EFFORT = "best_effort"


@dataclass(frozen=True, slots=True)
class ActorRef:
    kind: ActorKind
    id: str
    authority_scope: str


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    message_id: str
    schema_name: str
    schema_version: int
    kind: MessageKind
    mission_id: str
    sender: ActorRef
    recipient: ActorRef
    correlation_id: str
    payload: Mapping[str, JsonValue]
    idempotency_key: str | None = None
    sequence: int | None = None
    security_label: str = "project"


def delivery_guarantee(kind: MessageKind) -> DeliveryGuarantee:
    match kind:
        case MessageKind.PROGRESS:
            return DeliveryGuarantee.BEST_EFFORT
        case (
            MessageKind.COMMAND
            | MessageKind.EVENT
            | MessageKind.WORK_REQUEST
            | MessageKind.HUMAN_DECISION
            | MessageKind.ARTIFACT_REF
        ):
            return DeliveryGuarantee.AT_LEAST_ONCE
        case _ as unreachable:
            assert_never(unreachable)


def dedupe_key(message: MessageEnvelope) -> str:
    identity = message.idempotency_key or message.message_id
    return f"{message.mission_id}:{message.recipient.authority_scope}:{identity}"
