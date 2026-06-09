"""Engine adapters — execute + discuss lanes (H5)."""

from __future__ import annotations

from agent_lab.runtime.adapters.codex import (
    can_route_codex_proxy,
    codex_proxy_enabled,
    invoke_codex_proxy,
    probe_codex_proxy,
)
from agent_lab.runtime.adapters.discuss import discuss_agent_available, invoke_discuss
from agent_lab.runtime.adapters.execute import (
    DEFAULT_EXECUTE_AGENT,
    EXECUTE_AGENT_IDS,
    execute_agent_available,
    invoke_execute,
    invoke_repair,
    normalize_execute_agent,
    pick_repair_agent,
    verify_follow_up_text,
    verify_follow_ups,
)
from agent_lab.runtime.adapters.types import (
    ExecuteAgentId,
    ExecuteInvokeRequest,
    RepairInvokeRequest,
)

__all__ = [
    "can_route_codex_proxy",
    "codex_proxy_enabled",
    "invoke_codex_proxy",
    "probe_codex_proxy",
    "DEFAULT_EXECUTE_AGENT",
    "EXECUTE_AGENT_IDS",
    "ExecuteAgentId",
    "ExecuteInvokeRequest",
    "RepairInvokeRequest",
    "discuss_agent_available",
    "execute_agent_available",
    "invoke_discuss",
    "invoke_execute",
    "invoke_repair",
    "normalize_execute_agent",
    "pick_repair_agent",
    "verify_follow_up_text",
    "verify_follow_ups",
]
