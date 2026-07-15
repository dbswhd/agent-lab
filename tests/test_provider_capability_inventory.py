"""A1 (03-agent-runtime-context-memory.md) — provider capability inventory
producers stay importable.

Guards docs/redesign-2026-07/evidence/a1-provider-capability-inventory-2026-07-16.md:
every function the inventory cites as evidence must still exist, and the
per-provider capability/health branching it documents must still cover
exactly the providers listed (so a new provider being added silently
without capability/health coverage gets caught here, not discovered later
as a support gap).
"""

from __future__ import annotations

import importlib


REGISTERED_PRODUCERS = (
    ("agent_lab.agent.health", "agent_health_row"),
    ("agent_lab.agent.health", "build_agent_health"),
    ("agent_lab.agent.health", "build_health_payload"),
    ("agent_lab.room.agent_capabilities", "get_agent_capabilities"),
    ("agent_lab.agent.stream_parser", "parse_codex_json_event"),
    ("agent_lab.agent.stream_parser", "parse_claude_json_event"),
    ("agent_lab.runtime.adapters.execute", "invoke_execute"),
    ("agent_lab.runtime.adapters.execute", "execute_agent_available"),
    ("agent_lab.runtime.adapters.discuss", "invoke_discuss"),
    ("agent_lab.runtime.adapters.discuss", "discuss_agent_available"),
)

HEALTH_ROW_PROVIDER_IDS = frozenset({"cursor", "codex", "claude", "kimi", "kimi_work", "local"})
CAPABILITY_REGISTERED_PROVIDER_IDS = frozenset({"cursor", "codex", "claude", "kimi_work"})


def test_all_registered_capability_producers_still_exist() -> None:
    missing: list[str] = []
    for module_name, attr in REGISTERED_PRODUCERS:
        module = importlib.import_module(module_name)
        if not hasattr(module, attr):
            missing.append(f"{module_name}.{attr}")
    assert not missing, f"A1 capability inventory references removed producer(s): {missing}"


def test_agent_health_row_covers_exactly_the_documented_six_providers() -> None:
    from agent_lab.agent.health import agent_health_row

    for provider_id in HEALTH_ROW_PROVIDER_IDS:
        row = agent_health_row(provider_id)
        assert row["id"] == provider_id
        assert row.get("hint") != "unknown agent", f"{provider_id} fell through to the unknown-agent branch"


def test_tool_capability_registration_is_still_missing_for_kimi_and_local() -> None:
    """§2 finding — pins the gap so CX2-adjacent A2 work has to make an explicit
    decision about kimi/local tool capabilities instead of it staying silent."""
    from agent_lab.room.agent_capabilities import _CAPABILITY_AGENTS

    assert set(_CAPABILITY_AGENTS) == CAPABILITY_REGISTERED_PROVIDER_IDS
    assert "kimi" not in _CAPABILITY_AGENTS
    assert "local" not in _CAPABILITY_AGENTS
