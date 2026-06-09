"""Engine adapter request types (H5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

ExecuteAgentId = Literal["cursor", "codex"]
DiscussAgentId = Literal["cursor", "codex", "claude"]

EXECUTE_AGENT_IDS: frozenset[str] = frozenset({"cursor", "codex"})
DEFAULT_EXECUTE_AGENT: ExecuteAgentId = "cursor"


@dataclass(slots=True)
class ExecuteInvokeRequest:
    """Payload for execute-lane agent invocation."""

    system: str
    user: str
    permissions: dict[str, Any]
    cwd: Path
    verify_follow_ups: list[str] = field(default_factory=list)
    on_activity: Any | None = None
    session_folder: Path | None = None
    inbox_mcp: bool = False
    # Inbox MCP session path (Cursor plan → build GO → implement).
    plan_phase_user: str | None = None
    implement_phase_user: str | None = None
    inbox_gate: Callable[[], bool] | None = None


@dataclass(slots=True)
class RepairInvokeRequest:
    """Payload for L3 repair invocation."""

    system: str
    user: str
    permissions: dict[str, Any]
    cwd: Path
    verify_follow_ups: list[str] = field(default_factory=list)
