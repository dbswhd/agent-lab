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
import inspect


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
    ("agent_lab.agent.thread_resume", "normalize_agent_thread_bindings"),
    ("agent_lab.agent.thread_catalog", "AGENT_IDS"),
)

HEALTH_ROW_PROVIDER_IDS = frozenset({"cursor", "codex", "claude", "kimi", "kimi_work", "local"})
CAPABILITY_REGISTERED_PROVIDER_IDS = frozenset({"cursor", "codex", "claude", "kimi_work"})

# §4 (2026-07-16 correction) — cancel is agent_lab.run.control's is_cancelled()/
# register_child_process(), not a per-provider "cancel" function by name.
CANCEL_CAPABLE_PROVIDER_MODULES = {
    "claude": "agent_lab.claude.cli",
    "codex": "agent_lab.codex.cli",
    "cursor": "agent_lab.cursor.provider",
    "kimi_work": "agent_lab.kimi.control_client",
}
CANCEL_INCAPABLE_PROVIDER_MODULES = {
    "kimi": "agent_lab.kimi.provider",
    "local": "agent_lab.local.provider",
}


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


def test_cancel_support_matches_the_documented_four_provider_split() -> None:
    """§4 correction — cancel is real, via agent_lab.run.control's is_cancelled()/
    register_child_process(), for exactly the same 4 providers that have tool
    capabilities (§2). kimi/local have neither."""
    for module_name in CANCEL_CAPABLE_PROVIDER_MODULES.values():
        source = inspect.getsource(importlib.import_module(module_name))
        assert "is_cancelled" in source, f"{module_name} no longer polls is_cancelled() — update A1 §4"

    for module_name in CANCEL_INCAPABLE_PROVIDER_MODULES.values():
        source = inspect.getsource(importlib.import_module(module_name))
        assert "run.control" not in source and "is_cancelled" not in source, (
            f"{module_name} now references run.control — A1 §4's kimi/local cancel gap is closed, update the doc"
        )


def test_thread_resume_covers_exactly_three_providers() -> None:
    """§4 — resume (thread continuation) covers cursor/codex/claude only;
    kimi_work has cancel but not resume, an asymmetry worth keeping visible."""
    from agent_lab.agent.thread_catalog import AGENT_IDS

    assert set(AGENT_IDS) == {"cursor", "codex", "claude"}
