"""MCP tool surface contract — allowed read tools and forbidden execute/full-json paths."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

# Never expose these tools on any trading MCP server.
FORBIDDEN_TOOLS_GLOBAL: frozenset[str] = frozenset(
    {
        "execute_order",
        "approve_proposal",
        "arm_live",
        "read_notebook",
        "read_full_backtest_json",
        "read_full_json",
        "read_ipynb",
        "open_notebook",
    }
)

# quant-trading MCP — control plane ingest + compact market/card reads.
QUANT_TRADING_REQUIRED: frozenset[str] = frozenset(
    {
        "get_backtest_card",
        "get_data_freshness",
        "get_kill_switch_status",
        "get_portfolio_snapshot",
        "get_quote",
        "list_eligible_strategies",
        "list_pending_proposals",
    }
)

QUANT_TRADING_ALLOWED: frozenset[str] = QUANT_TRADING_REQUIRED | frozenset(
    {
        "create_trade_proposal",
        "get_control_plane_snapshot",
        "get_proposal",
        "ingest_proposal_batch",
        "ingest_trading_session",
    }
)

# agent-lab-research MCP — session reads + card verdict + critic (no ingest/execute).
RESEARCH_REQUIRED: frozenset[str] = frozenset(
    {
        "get_backtest_card",
        "get_data_freshness",
        "get_intraday_status",
        "get_pending_batch",
        "get_playbook",
        "get_portfolio_snapshot",
        "get_strategy_verdict",
        "list_wireup_candidates",
    }
)

RESEARCH_ALLOWED: frozenset[str] = RESEARCH_REQUIRED | frozenset(
    {
        "get_kill_switch_status",
        "get_overlay_signals",
        "get_playbook_summary",
        "get_quote",
        "list_pending_batch",
        "list_runnable_backtests",
        "review_proposal_thesis",
        "run_backtest_refresh",
        "wisdom_search",
    }
)

# Tools that must live on exactly one server (no overlap).
QUANT_TRADING_EXCLUSIVE: frozenset[str] = frozenset(
    {
        "create_trade_proposal",
        "ingest_proposal_batch",
        "ingest_trading_session",
        "list_pending_proposals",
        "get_control_plane_snapshot",
        "get_proposal",
        "list_eligible_strategies",
    }
)

RESEARCH_EXCLUSIVE: frozenset[str] = frozenset(
    {
        "get_intraday_status",
        "get_playbook",
        "get_pending_batch",
        "get_strategy_verdict",
        "list_wireup_candidates",
        "review_proposal_thesis",
        "run_backtest_refresh",
        "wisdom_search",
    }
)

_SERVER_SPECS: dict[str, dict[str, Any]] = {
    "agent-lab-research": {
        "module": "agent_lab.research_mcp_server",
        "attr": "mcp",
        "allowed": RESEARCH_ALLOWED,
        "required": RESEARCH_REQUIRED,
        "exclusive": RESEARCH_EXCLUSIVE,
    },
    "quant-trading": {
        "module": "quant_pipeline.quant_trading_mcp_server",
        "attr": "mcp",
        "allowed": QUANT_TRADING_ALLOWED,
        "required": QUANT_TRADING_REQUIRED,
        "exclusive": QUANT_TRADING_EXCLUSIVE,
    },
}


async def list_mcp_tool_names(mcp: Any) -> list[str]:
    tools = await mcp.list_tools()
    return sorted({str(t.name) for t in tools})


def load_mcp_instance(server: str) -> Any:
    spec = _SERVER_SPECS.get(server)
    if spec is None:
        raise KeyError(f"unknown MCP server: {server}")
    mod = importlib.import_module(str(spec["module"]))
    return getattr(mod, str(spec["attr"]))


async def collect_tool_names(server: str) -> list[str]:
    mcp = load_mcp_instance(server)
    return await list_mcp_tool_names(mcp)


def validate_mcp_tool_surface(
    tool_names: list[str],
    *,
    server: str,
) -> dict[str, Any]:
    """Return ok + issues for one MCP server's registered tools."""
    spec = _SERVER_SPECS[server]
    allowed: frozenset[str] = spec["allowed"]
    required: frozenset[str] = spec["required"]
    exclusive: frozenset[str] = spec["exclusive"]
    names = set(tool_names)

    issues: list[str] = []
    forbidden = sorted(names & FORBIDDEN_TOOLS_GLOBAL)
    if forbidden:
        issues.append(f"forbidden tools exposed: {', '.join(forbidden)}")

    unexpected = sorted(names - allowed)
    if unexpected:
        issues.append(f"unexpected tools: {', '.join(unexpected)}")

    missing = sorted(required - names)
    if missing:
        issues.append(f"missing required tools: {', '.join(missing)}")

    overlap = sorted(names & exclusive)
    other = "quant-trading" if server == "agent-lab-research" else "agent-lab-research"
    other_spec = _SERVER_SPECS[other]
    other_exclusive: frozenset[str] = other_spec["exclusive"]
    cross = sorted(names & other_exclusive)
    if cross:
        issues.append(f"tools belong on {other}: {', '.join(cross)}")

    return {
        "ok": not issues,
        "server": server,
        "tool_count": len(names),
        "tools": sorted(names),
        "issues": issues,
    }


async def audit_mcp_contracts() -> dict[str, Any]:
    """Validate both trading MCP servers against the contract."""
    reports: dict[str, Any] = {}
    all_ok = True
    for server in _SERVER_SPECS:
        names = await collect_tool_names(server)
        report = validate_mcp_tool_surface(names, server=server)
        reports[server] = report
        all_ok = all_ok and bool(report["ok"])
    return {"ok": all_ok, "servers": reports}
