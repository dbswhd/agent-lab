"""stdio MCP server — read-only session metrics for Room self-observation (S1)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agent-lab-session-metrics")


def _session_folder() -> Path:
    raw = os.getenv("AGENT_LAB_SESSION_FOLDER", "").strip()
    if not raw:
        raise RuntimeError("AGENT_LAB_SESSION_FOLDER is not set")
    folder = Path(raw).expanduser().resolve()
    if not folder.is_dir():
        raise RuntimeError(f"session folder not found: {folder}")
    return folder


@mcp.tool()
def get_session_metrics() -> dict[str, Any]:
    """Read-only KPI snapshot (score_session subset + turn_policy)."""
    from agent_lab.session.metrics_payload import build_session_metrics_payload

    return build_session_metrics_payload(_session_folder())


@mcp.tool()
def get_emergence_kpis() -> dict[str, Any]:
    """Emergence KPIs only — hybrid_action_rate, challenge_yield, recombination."""
    from agent_lab.session.metrics_payload import build_emergence_kpis_payload

    return build_emergence_kpis_payload(_session_folder())


@mcp.tool()
def get_turn_policy_snapshot() -> dict[str, Any]:
    """Current turn_policy snapshot from run.json."""
    from agent_lab.run.meta import read_run_meta
    from agent_lab.session.metrics_payload import build_turn_policy_snapshot

    return build_turn_policy_snapshot(read_run_meta(_session_folder()))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
