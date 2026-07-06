"""Runtime agent plugin table — dispatch layer keyed by ``provider_registry`` IDs."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from agent_lab.provider_registry import DEFAULT_ROSTER, get_provider

AgentId = Literal["cursor", "codex", "claude", "kimi", "kimi_work", "local"]

AGENT_IDS: tuple[AgentId, ...] = DEFAULT_ROSTER  # type: ignore[assignment]

_PLUGIN_MODULES: dict[AgentId, str] = {
    "cursor": "agent_lab.agents.cursor_agent",
    "codex": "agent_lab.agents.codex_agent",
    "claude": "agent_lab.agents.claude_agent",
    "kimi": "agent_lab.kimi.provider",
    "kimi_work": "agent_lab.kimi.work_provider",
    "local": "agent_lab.local.provider",
}


@dataclass(frozen=True)
class AgentPlugin:
    """One registered provider's runtime invoke surface (lazy module lookup for tests)."""

    id: AgentId
    module: str

    def _mod(self) -> Any:
        return importlib.import_module(self.module)

    def is_available(self) -> bool:
        return self._mod().is_available()

    def model_label(self) -> str:
        mod = self._mod()
        if self.id in ("codex", "claude"):
            cli = importlib.import_module("agent_lab.codex.cli" if self.id == "codex" else "agent_lab.claude.cli")
            return cli.model_label()
        return mod.model_label()

    def respond(self, system: str, user: str, **kwargs: Any) -> str:
        return self._mod().respond(system, user, **kwargs)


def _build_plugins() -> dict[AgentId, AgentPlugin]:
    return {agent_id: AgentPlugin(agent_id, module) for agent_id, module in _PLUGIN_MODULES.items()}


_PLUGINS: dict[AgentId, AgentPlugin] | None = None


def plugins() -> dict[AgentId, AgentPlugin]:
    global _PLUGINS
    if _PLUGINS is None:
        _PLUGINS = _build_plugins()
    return _PLUGINS


def get_plugin(agent: AgentId) -> AgentPlugin:
    return plugins()[agent]


def label(agent: AgentId) -> str:
    spec = get_provider(agent)
    if spec:
        return spec.label
    return agent


def reset_plugins_for_tests() -> None:
    """Test helper — rebuild plugin table after monkeypatching provider modules."""
    global _PLUGINS
    _PLUGINS = None


def call_plugin_respond(
    agent: AgentId,
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    scribe: bool = False,
    on_activity: Callable[[str], None] | None = None,
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None = None,
    session_folder: str | Any | None = None,
    request_structured_envelope: bool = False,
    inbox_mcp: bool = False,
) -> str:
    plugin = get_plugin(agent)
    kwargs: dict[str, Any] = {
        "permissions": permissions,
        "on_activity": on_activity,
        "on_bridge_event": on_bridge_event,
        "session_folder": session_folder,
        "request_structured_envelope": request_structured_envelope,
        "inbox_mcp": inbox_mcp,
    }
    if agent == "claude":
        kwargs["scribe"] = scribe
    return plugin.respond(system, user, **kwargs)
