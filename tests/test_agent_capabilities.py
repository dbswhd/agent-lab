"""Agent permission defaults and tool-rule wiring."""

from __future__ import annotations

from agent_lab.agent_permissions import (
    cursor_runtime_block,
    normalize_agent_permissions,
    normalize_cursor_permissions,
    permission_preamble,
)
from agent_lab.context_bundle import build_context_bundle
from agent_lab.room_context import agent_tool_rules


def test_full_agent_permissions_normalize():
    perms = normalize_agent_permissions({})
    assert perms["cursor"]["tools"] is True
    assert perms["cursor"]["local_pipeline"] is True
    assert perms["cursor"]["local_lecture_script"] is True
    assert perms["claude"]["write"] is True
    assert perms["claude"]["local_pipeline"] is True
    assert perms["codex"]["cli"] is True


def test_cursor_defaults_enable_tools():
    perms = normalize_cursor_permissions({})
    assert perms["cursor"]["tools"] is True
    assert perms["cursor"]["local_agent_lab"] is True


def test_cursor_runtime_block_mentions_tools():
    block = cursor_runtime_block({})
    assert "NOT text-only" in block
    assert "tools" in block.lower()


def test_coordination_in_bundle():
    bundle = build_context_bundle(
        "topic",
        [],
        "codex",
        permission_lines=permission_preamble({}, "codex"),
        permissions=normalize_agent_permissions({}),
    )
    assert "Multi-agent coordination" in bundle.render()


def test_cursor_tool_rules_in_bundle():
    bundle = build_context_bundle(
        "topic",
        [],
        "cursor",
        permission_lines=permission_preamble({}, "cursor"),
        permissions=normalize_cursor_permissions({}),
    )
    rendered = bundle.render()
    assert agent_tool_rules("cursor")[:20] in rendered
    assert "read or search" in rendered.lower() or "read" in rendered.lower()


def test_permission_preamble_peer_agents_return_empty_string() -> None:
    perms = {"_discuss_cwd": "/tmp/ws"}
    assert permission_preamble(perms, "kimi_work") == ""
    assert permission_preamble(perms, "kimi") == ""
    assert permission_preamble(perms, "local") == ""
