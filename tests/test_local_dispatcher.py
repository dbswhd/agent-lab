from __future__ import annotations

import pytest

from agent_lab.mission.dispatcher import DispatcherError, DispatchReceipt, LocalDispatcher
from agent_lab.mission.messages import ActorKind, ActorRef, MessageEnvelope, MessageKind, dedupe_key


def _command(message_id: str, key: str) -> MessageEnvelope:
    return MessageEnvelope(
        message_id=message_id,
        schema_name="ApprovePlan",
        schema_version=1,
        kind=MessageKind.COMMAND,
        mission_id="m-1",
        sender=ActorRef(ActorKind.HUMAN, "local", "plan.approve"),
        recipient=ActorRef(ActorKind.CONDUCTOR, "mission", "mission.write"),
        correlation_id="c-1",
        payload={"plan_hash": "abc"},
        idempotency_key=key,
    )


def test_local_dispatcher_applies_command_effect_once() -> None:
    calls: list[str] = []
    dispatcher = LocalDispatcher()
    dispatcher.register_command("ApprovePlan", lambda message: calls.append(message.message_id))
    first = dispatcher.dispatch(_command("msg-1", "approve:m-1:abc"))
    second = dispatcher.dispatch(_command("msg-2", "approve:m-1:abc"))
    assert first == DispatchReceipt(handled=True, duplicate=False)
    assert second == DispatchReceipt(handled=False, duplicate=True)
    assert calls == ["msg-1"]


def test_local_dispatcher_requires_command_owner() -> None:
    with pytest.raises(DispatcherError):
        LocalDispatcher().dispatch(_command("msg-1", "approve:m-1:abc"))


def test_dedupe_key_is_scoped_to_mission_and_authority() -> None:
    first = _command("msg-1", "same")
    second = MessageEnvelope(
        message_id="msg-2",
        schema_name="ApprovePlan",
        schema_version=1,
        kind=MessageKind.COMMAND,
        mission_id="m-2",
        sender=first.sender,
        recipient=first.recipient,
        correlation_id="c-2",
        payload=first.payload,
        idempotency_key="same",
    )

    assert dedupe_key(first) != dedupe_key(second)


def test_dispatcher_rejects_unauthorized_command_sender() -> None:
    message = MessageEnvelope(
        message_id="msg-tool",
        schema_name="ApprovePlan",
        schema_version=1,
        kind=MessageKind.COMMAND,
        mission_id="m-1",
        sender=ActorRef(ActorKind.TOOL, "tool", "none"),
        recipient=ActorRef(ActorKind.SYSTEM, "system", "none"),
        correlation_id="c-1",
        payload={"plan_hash": "abc"},
    )
    dispatcher = LocalDispatcher()
    dispatcher.register_command("ApprovePlan", lambda _: None)

    with pytest.raises(DispatcherError, match="authority"):
        dispatcher.dispatch(message)
