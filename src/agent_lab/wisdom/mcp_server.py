"""stdio MCP server for cross-session Wisdom Index (Phase 1 pilot).

Exposes wisdom_record / wisdom_recall / wisdom_list_recent / wisdom_status_check
as read+write MCP tools for Claude and Codex agents.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP

from agent_lab.wisdom.store import (
    wisdom_append,
    wisdom_list_recent,
    wisdom_query,
    wisdom_status,
)

mcp = FastMCP("agent-lab-wisdom")

WISDOM_MCP_SERVER_NAME = "agent-lab-wisdom"


@mcp.tool()
def wisdom_recall(query: str, k: int = 5) -> dict[str, Any]:
    """Search the cross-session Wisdom Index for relevant past learnings.

    Returns up to k entries whose content or tags match the query keywords.
    """
    hits = wisdom_query(query, k=max(1, min(k, 20)))
    return {
        "ok": True,
        "query": query,
        "hit_count": len(hits),
        "hits": [asdict(e) for e in hits],
    }


@mcp.tool()
def wisdom_record(content: str, tags: str = "", source_ref: str = "") -> dict[str, Any]:
    """Record a new learning into the cross-session Wisdom Index.

    - content: the insight or finding to persist
    - tags: comma-separated labels (e.g. "auth,jwt,pattern")
    - source_ref: optional file ref (e.g. "src/auth.py:42-60")
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    session_id = (os.getenv("AGENT_LAB_SESSION_FOLDER") or "").strip() or None
    entry = wisdom_append(
        content,
        tags=tag_list,
        session_id=session_id,
        source_ref=source_ref.strip() or None,
    )
    return {
        "ok": True,
        "id": entry.id,
        "timestamp": entry.timestamp,
        "tags": entry.tags,
        "source_ref": entry.source_ref,
    }


@mcp.tool()
def wisdom_list(limit: int = 10) -> dict[str, Any]:
    """List recent wisdom entries from the cross-session index, newest first."""
    entries = wisdom_list_recent(limit=max(1, min(limit, 50)))
    return {
        "ok": True,
        "entry_count": len(entries),
        "entries": [asdict(e) for e in entries],
    }


@mcp.tool()
def wisdom_index_status() -> dict[str, Any]:
    """Return the status and statistics of the Wisdom Index store."""
    return wisdom_status()


if __name__ == "__main__":
    mcp.run()
