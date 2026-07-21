"""Assembled agent context payload types (F12 — stdlib only)."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any

_TRUE = frozenset({"1", "true", "yes", "on"})


def _env_on(name: str) -> bool:
    """Deliberately NOT ``agent_lab.env_flags.env_bool`` — ``agent_lab.core``
    is enforced dependency-zero/stdlib-only by
    ``test_no_layer_cycles.py::test_core_has_no_agent_lab_imports``, so this
    package must keep its own tiny copy rather than import the shared one."""
    return (os.getenv(name) or "").strip().lower() in _TRUE


@dataclass
class ContextBundleMeta:
    agent: str
    parallel_round: int
    review_mode: bool
    turns_omitted: int = 0
    chars_omitted: int = 0
    peer_message_count: int = 0
    peer_deduped: int = 0
    pinned_message_count: int = 0
    layer_chars: dict[str, int] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    budget_pct: float = 0.0
    trim_level: str = "ok"
    messages_in_payload: int = 0
    messages_in_turn: int = 0
    messages_in_session: int = 0
    numbered_context: bool = False
    line_range: str = ""
    efficiency_mode: bool = False
    slim_context: bool = False
    pin_capped: bool = False
    capability_cwd: str = ""
    context_mode: str = "full"
    recent_max_chars: int | None = None
    peer_suppressed: bool = False
    repo_layer: str | None = None
    repo_map_enabled: bool | None = None
    compact_tool_output: bool | None = None
    tool_output_chars_truncated: int = 0

    def to_dict(self) -> dict[str, Any]:
        row = {
            "agent": self.agent,
            "parallel_round": self.parallel_round,
            "review_mode": self.review_mode,
            "turns_omitted": self.turns_omitted,
            "chars_omitted": self.chars_omitted,
            "peer_message_count": self.peer_message_count,
            "peer_deduped": self.peer_deduped,
            "pinned_message_count": self.pinned_message_count,
            "layer_chars": dict(self.layer_chars),
            "limits": dict(self.limits),
            "budget_pct": self.budget_pct,
            "trim_level": self.trim_level,
            "messages_in_payload": self.messages_in_payload,
            "messages_in_turn": self.messages_in_turn,
            "messages_in_session": self.messages_in_session,
            "numbered_context": self.numbered_context,
            "line_range": self.line_range,
            "efficiency_mode": self.efficiency_mode,
            "slim_context": self.slim_context,
            "pin_capped": self.pin_capped,
            "context_mode": self.context_mode,
        }
        if self.capability_cwd:
            row["capability_cwd"] = self.capability_cwd
        if self.recent_max_chars is not None:
            row["recent_max_chars"] = self.recent_max_chars
        if self.peer_suppressed:
            row["peer_suppressed"] = True
        repo_map_enabled = self.repo_map_enabled
        if repo_map_enabled is None:
            repo_map_enabled = _env_on("AGENT_LAB_REPO_MAP")
        compact_tool_output = self.compact_tool_output
        if compact_tool_output is None:
            compact_tool_output = _env_on("AGENT_LAB_COMPACT_TOOL_OUTPUT")
        row["repo_layer"] = self.repo_layer or ("repo_map" if repo_map_enabled else "repo_tree")
        row["repo_map_enabled"] = repo_map_enabled
        row["compact_tool_output"] = compact_tool_output
        if self.tool_output_chars_truncated:
            row["tool_output_chars_truncated"] = self.tool_output_chars_truncated
        return row


@dataclass
class ContextBundle:
    constraints: str
    plan_open: str
    bridge: str
    recent: str
    peer: str
    guidance_block: str
    connect_hint: str
    claude_tools: str = ""
    follow_up: str = ""
    turn_state: str = ""
    meta: ContextBundleMeta = field(default_factory=lambda: ContextBundleMeta("", 0, False))

    def render(self) -> str:
        parts = [self.constraints, self.plan_open]
        if self.turn_state.strip():
            parts.append(self.turn_state)
        if self.bridge.strip():
            parts.append(self.bridge)
        parts.extend([self.recent])
        if self.peer.strip():
            parts.append(self.peer)
        parts.append(self.guidance_block)
        if self.connect_hint.strip():
            parts.append(self.connect_hint)
        block = "\n\n".join(p for p in parts if p)
        if self.claude_tools.strip():
            block = f"{block}\n\n---\n{self.claude_tools.strip()}"
        if self.follow_up.strip():
            block = f"{block}\n{self.follow_up.strip()}"
        return block
