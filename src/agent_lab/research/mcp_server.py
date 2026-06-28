"""stdio MCP server — thin runtime research read (playbook, pending batch, wisdom)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from mcp.server.fastmcp import FastMCP

from agent_lab.research.mcp_read import (
    read_pending_batch_summary,
    read_playbook_summary,
    resolve_session_folder,
)

mcp = FastMCP("agent-lab-research")


def _session_folder() -> Path:
    return resolve_session_folder()


@mcp.tool()
def get_playbook(max_chars: int = 4000) -> dict[str, Any]:
    """Return 「오늘 장중 행동」playbook summary from session or pipeline data/agentic."""
    cap = max(500, min(int(max_chars or 4000), 8000))
    return cast(dict[str, Any], read_playbook_summary(_session_folder(), max_chars=cap))


@mcp.tool()
def get_playbook_summary(max_chars: int = 4000) -> dict[str, Any]:
    """Alias for get_playbook — compact intraday playbook for thin runtime agent."""
    return cast(dict[str, Any], get_playbook(max_chars=max_chars))


@mcp.tool()
def get_pending_batch() -> dict[str, Any]:
    """Return compact proposal_batch / proposal_delta summary from current session."""
    return cast(dict[str, Any], read_pending_batch_summary(_session_folder()))


@mcp.tool()
def list_pending_batch() -> dict[str, Any]:
    """Alias for get_pending_batch."""
    return cast(dict[str, Any], get_pending_batch())


@mcp.tool()
def get_quote(symbol: str, market: str = "kr") -> dict[str, Any]:
    """Compact quote for one symbol (mock-first; AGENT_LAB_QUOTE_MODE=kis for KIS)."""
    from agent_lab.pipeline_market_read import get_quote as _quote

    return _quote(symbol, market)


@mcp.tool()
def get_data_freshness() -> dict[str, Any]:
    """Pipeline data freshness (spec91); blocking flag for trade_allowed."""
    from agent_lab.pipeline_market_read import get_data_freshness as _fresh

    return _fresh()


@mcp.tool()
def get_portfolio_snapshot() -> dict[str, Any]:
    """Mock-first portfolio snapshot (cash, equity, positions)."""
    from agent_lab.pipeline_market_read import get_portfolio_snapshot as _portfolio

    return _portfolio()


@mcp.tool()
def get_overlay_signals() -> dict[str, Any]:
    """KR overlay signals (kr_kospi_v1 position, action flag)."""
    from agent_lab.pipeline_market_read import get_overlay_signals as _overlay

    return _overlay()


@mcp.tool()
def list_runnable_backtests() -> dict[str, Any]:
    """Refs with registered pipeline backtest runner scripts."""
    from agent_lab.backtest_runner_delegate import list_runnable_backtests as _list

    return _list()


@mcp.tool()
def run_backtest_refresh(ref: str, dry_run: bool = True) -> dict[str, Any]:
    """Run pipeline backtest for ref; returns compact card (dry_run=True by default)."""
    from agent_lab.backtest_runner_delegate import run_backtest_delegate

    return run_backtest_delegate(ref, dry_run=bool(dry_run))


@mcp.tool()
def get_strategy_verdict(ref: str) -> dict[str, Any]:
    """Return verdict summary for a backtest ref (slug or source_file path). No full JSON."""
    from agent_lab.pipeline_research_read import get_strategy_verdict as _verdict

    return _verdict(ref)


@mcp.tool()
def get_backtest_card(ref: str) -> dict[str, Any]:
    """Return compact ResearchArtifactCard (~1KB) for ref."""
    from agent_lab.pipeline_research_read import get_backtest_card as _card

    return _card(ref)


@mcp.tool()
def list_wireup_candidates(limit: int = 25) -> dict[str, Any]:
    """List PASS backtest cards eligible for proposal (cached when available)."""
    from agent_lab.pipeline_research_read import list_wireup_candidates as _list

    cap = max(1, min(int(limit or 25), 100))
    return _list(limit=cap)


@mcp.tool()
def get_kill_switch_status() -> dict[str, Any]:
    """EMERGENCY_STOP flag read — trade_allowed=false when enabled."""
    from agent_lab.pipeline_market_read import read_kill_switch
    from agent_lab.pipeline_research_read import resolve_pipeline_root

    root = resolve_pipeline_root()
    enabled = read_kill_switch(root)
    return {
        "ok": True,
        "pipeline_root": str(root),
        "kill_switch_enabled": enabled,
        "trade_allowed": not enabled,
    }


@mcp.tool()
def get_intraday_status() -> dict[str, Any]:
    """Thin runtime bundle: playbook, batch, control-plane pending (no Room)."""
    from agent_lab.trading_mission.thin_runtime import get_intraday_status as _status

    return _status()


@mcp.tool()
def review_proposal_thesis(
    thesis: str,
    ref: str,
    quote_json: str = "",
    symbol: str = "",
    agent_confidence: float | None = None,
) -> dict[str, Any]:
    """Critic review: objections, confidence_cap, missing_evidence (no full backtest JSON)."""
    from agent_lab.proposal_critic import review_proposal_thesis as _review

    conf = None if agent_confidence is None else float(agent_confidence)
    sym = symbol.strip() or None
    quote = quote_json if quote_json else None
    return _review(
        thesis,
        ref,
        quote,
        symbol=sym,
        agent_confidence=conf,
    )


@mcp.tool()
def wisdom_search(query: str, k: int = 3) -> dict[str, Any]:
    """Search session wisdom index (trading tags, blocked proposals, mission notes)."""
    from agent_lab.wisdom.index import public_wisdom_search_payload

    folder = _session_folder()
    limit = max(1, min(int(k or 3), 10))
    return public_wisdom_search_payload(
        folder,
        query=str(query or "").strip(),
        limit=limit,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
