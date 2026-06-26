"""MCP tool surface contract — allowed read tools and forbidden execute/full-json paths."""

from __future__ import annotations

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
        "write_file",
        "execute",
        "read_full_file",
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

CODE_MEMORY_REQUIRED: frozenset[str] = frozenset({"code_memory_search"})
CODE_MEMORY_ALLOWED: frozenset[str] = CODE_MEMORY_REQUIRED | frozenset({"code_memory_status"})
CODE_MEMORY_EXCLUSIVE: frozenset[str] = frozenset({"code_memory_search", "code_memory_status"})

# agent-lab-wisdom MCP — cross-session read+write Wisdom Index.
WISDOM_REQUIRED: frozenset[str] = frozenset({"wisdom_recall", "wisdom_record"})
WISDOM_ALLOWED: frozenset[str] = WISDOM_REQUIRED | frozenset({"wisdom_list", "wisdom_index_status"})
WISDOM_EXCLUSIVE: frozenset[str] = frozenset({"wisdom_recall", "wisdom_record", "wisdom_list", "wisdom_index_status"})

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
    "agent-lab-code-memory": {
        "module": "agent_lab.code_memory_mcp_server",
        "attr": "mcp",
        "allowed": CODE_MEMORY_ALLOWED,
        "required": CODE_MEMORY_REQUIRED,
        "exclusive": CODE_MEMORY_EXCLUSIVE,
    },
    "agent-lab-wisdom": {
        "module": "agent_lab.wisdom_mcp_server",
        "attr": "mcp",
        "allowed": WISDOM_ALLOWED,
        "required": WISDOM_REQUIRED,
        "exclusive": WISDOM_EXCLUSIVE,
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

    for other, other_spec in _SERVER_SPECS.items():
        if other == server:
            continue
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


def validate_code_memory_hit(hit: dict[str, Any]) -> list[str]:
    """Validate one code-memory hit carries a stable source reference."""
    issues: list[str] = []
    for key in ("path", "start_line", "end_line", "source_ref", "snippet", "fresh"):
        if not hit.get(key):
            issues.append(f"missing or empty hit field: {key}")

    path = hit.get("path")
    start_line = hit.get("start_line")
    end_line = hit.get("end_line")
    source_ref = hit.get("source_ref")

    if not isinstance(start_line, int):
        issues.append("start_line must be an int")
    if not isinstance(end_line, int):
        issues.append("end_line must be an int")
    if isinstance(start_line, int) and start_line < 1:
        issues.append("start_line must be >= 1")
    if isinstance(start_line, int) and isinstance(end_line, int) and end_line < start_line:
        issues.append("end_line must be >= start_line")
    if isinstance(path, str) and isinstance(start_line, int) and isinstance(end_line, int):
        expected_source_ref = f"{path}:{start_line}-{end_line}"
        if source_ref != expected_source_ref:
            issues.append(f"source_ref must equal {expected_source_ref}")

    return issues


def validate_code_memory_search_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the public code-memory search payload shape and hit source refs."""
    issues: list[str] = []
    required = ("ok", "enabled", "mode", "query", "hit_count", "stale_hit_count", "hits", "index")
    for key in required:
        if key not in payload:
            issues.append(f"missing payload field: {key}")

    hits = payload.get("hits")
    if isinstance(hits, list):
        for idx, hit in enumerate(hits):
            if not isinstance(hit, dict):
                issues.append(f"hit {idx} must be a dict")
                continue
            for issue in validate_code_memory_hit(hit):
                issues.append(f"hit {idx}: {issue}")
    elif "hits" in payload:
        issues.append("hits must be a list")

    return {"ok": not issues, "issues": issues}


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
