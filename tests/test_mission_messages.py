from __future__ import annotations

from agent_lab.mission.messages import (
    ActorKind,
    ActorRef,
    DeliveryGuarantee,
    MessageEnvelope,
    MessageKind,
    delivery_guarantee,
    dedupe_key,
)


def test_command_envelope_carries_authority_and_correlation() -> None:
    message = MessageEnvelope(
        message_id="msg-1",
        schema_name="ApprovePlan",
        schema_version=1,
        kind=MessageKind.COMMAND,
        mission_id="m-1",
        sender=ActorRef(ActorKind.HUMAN, "local", "plan.approve"),
        recipient=ActorRef(ActorKind.CONDUCTOR, "mission", "mission.write"),
        correlation_id="cmd-1",
        payload={"plan_hash": "abc"},
        idempotency_key="approve:m-1:abc",
    )
    assert message.sender.authority_scope == "plan.approve"
    assert dedupe_key(message) == "m-1:mission.write:approve:m-1:abc"


def test_progress_is_best_effort_but_command_is_at_least_once() -> None:
    progress = MessageEnvelope(
        message_id="msg-1",
        schema_name="AgentProgress",
        schema_version=1,
        kind=MessageKind.PROGRESS,
        mission_id="m-1",
        sender=ActorRef(ActorKind.AGENT, "codex", "activity.progress"),
        recipient=ActorRef(ActorKind.SYSTEM, "projection", "projection.write"),
        correlation_id="a-1",
        payload={"text": "working"},
    )
    assert delivery_guarantee(progress.kind) is DeliveryGuarantee.BEST_EFFORT
    assert delivery_guarantee(MessageKind.COMMAND) is DeliveryGuarantee.AT_LEAST_ONCE


def test_message_envelope_is_immutable() -> None:
    message = MessageEnvelope(
        message_id="msg-1",
        schema_name="PlanApproved",
        schema_version=1,
        kind=MessageKind.EVENT,
        mission_id="m-1",
        sender=ActorRef(ActorKind.CONDUCTOR, "mission", "mission.write"),
        recipient=ActorRef(ActorKind.SYSTEM, "projection", "projection.read"),
        correlation_id="m-1",
        payload={"plan_hash": "abc"},
    )
    assert message.kind is MessageKind.EVENT
