"""Mailbox harvest and agent payload block."""

from __future__ import annotations

from agent_lab.agent_envelope import AgentEnvelope
from agent_lab.room_mailbox import (
    append_mailbox_message,
    build_mailbox_block,
    harvest_mailbox_from_turn,
    unread_for_agent,
)


class _Msg:
    def __init__(self, role, agent=None, content="", envelope=None, visibility="human"):
        self.role = role
        self.agent = agent
        self.content = content
        self.envelope = envelope
        self.visibility = visibility


def test_append_and_unread():
    meta: dict = {}
    append_mailbox_message(
        meta, from_agent="cursor", to_agent="codex", body="review my patch"
    )
    assert len(unread_for_agent(meta, "codex")) == 1
    block = build_mailbox_block(meta, "codex")
    assert "review my patch" in block
    assert len(unread_for_agent(meta, "codex")) == 0


def test_harvest_message_envelope():
    meta: dict = {}
    msgs = [
        _Msg("user", content="go"),
        _Msg(
            "agent",
            agent="cursor",
            content="please check",
            envelope=AgentEnvelope(
                act="MESSAGE",
                refs=["t-abc"],
                to="codex",
                message="please check",
            ).to_dict(),
        ),
    ]
    created = harvest_mailbox_from_turn(meta, msgs, human_turn=1)
    assert len(created) == 1
    assert created[0]["to"] == "codex"
    assert created[0].get("task_id") == "t-abc"
