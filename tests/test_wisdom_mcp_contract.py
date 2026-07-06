"""Contract validation for agent-lab-wisdom MCP server tool surface."""

from __future__ import annotations

import asyncio


from agent_lab.mcp_tool_contract import (
    FORBIDDEN_TOOLS_GLOBAL,
    WISDOM_ALLOWED,
    WISDOM_EXCLUSIVE,
    WISDOM_REQUIRED,
    collect_tool_names,
    validate_mcp_tool_surface,
)


def test_wisdom_contract_sets_are_consistent() -> None:
    assert WISDOM_REQUIRED <= WISDOM_ALLOWED
    assert WISDOM_EXCLUSIVE <= WISDOM_ALLOWED
    assert WISDOM_REQUIRED <= WISDOM_EXCLUSIVE


def test_wisdom_tools_not_globally_forbidden() -> None:
    assert not (WISDOM_ALLOWED & FORBIDDEN_TOOLS_GLOBAL), (
        f"Wisdom tools in forbidden list: {WISDOM_ALLOWED & FORBIDDEN_TOOLS_GLOBAL}"
    )


def test_wisdom_server_tool_surface() -> None:
    tool_names = asyncio.run(collect_tool_names("agent-lab-wisdom"))
    result = validate_mcp_tool_surface(tool_names, server="agent-lab-wisdom")
    assert result["ok"], f"Wisdom MCP contract violations: {result['issues']}"
    assert "wisdom_recall" in result["tools"]
    assert "wisdom_record" in result["tools"]


def test_wisdom_tools_exclusive_to_wisdom_server() -> None:
    # wisdom tools must not appear on other servers
    from agent_lab.mcp_tool_contract import CODE_MEMORY_EXCLUSIVE, QUANT_TRADING_EXCLUSIVE, RESEARCH_EXCLUSIVE

    for other_excl, name in [
        (CODE_MEMORY_EXCLUSIVE, "code-memory"),
        (QUANT_TRADING_EXCLUSIVE, "quant-trading"),
        (RESEARCH_EXCLUSIVE, "research"),
    ]:
        cross = WISDOM_EXCLUSIVE & other_excl
        assert not cross, f"Wisdom tools overlap with {name} exclusive set: {cross}"


def test_wisdom_server_no_forbidden_tools() -> None:
    tool_names = asyncio.run(collect_tool_names("agent-lab-wisdom"))
    forbidden_exposed = set(tool_names) & FORBIDDEN_TOOLS_GLOBAL
    assert not forbidden_exposed, f"Forbidden tools on wisdom server: {forbidden_exposed}"
