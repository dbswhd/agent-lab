from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import assert_never

from agent_lab.mission.messages import ActorKind, MessageEnvelope, MessageKind, dedupe_key

MessageHandler = Callable[[MessageEnvelope], None]


class DispatcherError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class DispatchReceipt:
    handled: bool
    duplicate: bool


class LocalDispatcher:
    def __init__(self) -> None:
        self._commands: dict[str, MessageHandler] = {}
        self._subscriptions: dict[str, list[MessageHandler]] = {}
        self._seen_commands: set[str] = set()

    def register_command(self, schema_name: str, handler: MessageHandler) -> None:
        if schema_name in self._commands:
            raise DispatcherError(f"command owner already registered: {schema_name}")
        self._commands[schema_name] = handler

    def subscribe(self, schema_name: str, handler: MessageHandler) -> None:
        self._subscriptions.setdefault(schema_name, []).append(handler)

    def dispatch(self, message: MessageEnvelope) -> DispatchReceipt:
        match message.kind:
            case MessageKind.COMMAND | MessageKind.HUMAN_DECISION | MessageKind.WORK_REQUEST:
                return self._dispatch_command(message)
            case MessageKind.EVENT | MessageKind.PROGRESS | MessageKind.ARTIFACT_REF:
                return self._dispatch_event(message)
            case _ as unreachable:
                assert_never(unreachable)

    def _dispatch_command(self, message: MessageEnvelope) -> DispatchReceipt:
        if message.schema_version < 1 or not message.mission_id or not message.correlation_id:
            raise DispatcherError("invalid command envelope")
        if message.sender.kind not in {ActorKind.HUMAN, ActorKind.CONDUCTOR, ActorKind.AGENT, ActorKind.EXTENSION}:
            raise DispatcherError("command sender lacks authority")
        if message.recipient.authority_scope != "mission.write":
            raise DispatcherError("command recipient lacks mission authority")
        key = dedupe_key(message)
        if key in self._seen_commands:
            return DispatchReceipt(handled=False, duplicate=True)
        handler = self._commands.get(message.schema_name)
        if handler is None:
            raise DispatcherError(f"command owner not registered: {message.schema_name}")
        handler(message)
        self._seen_commands.add(key)
        return DispatchReceipt(handled=True, duplicate=False)

    def _dispatch_event(self, message: MessageEnvelope) -> DispatchReceipt:
        handlers = tuple(self._subscriptions.get(message.schema_name, ()))
        for handler in handlers:
            handler(message)
        return DispatchReceipt(handled=bool(handlers), duplicate=False)
