"""stdio MCP server — ask_human / propose_build bridge to Human Inbox."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agent-lab-inbox")


def _session_folder() -> Path:
    raw = os.getenv("AGENT_LAB_SESSION_FOLDER", "").strip()
    if not raw:
        raise RuntimeError("AGENT_LAB_SESSION_FOLDER is not set")
    folder = Path(raw).expanduser().resolve()
    if not folder.is_dir():
        raise RuntimeError(f"session folder not found: {folder}")
    return folder


def _normalize_options(options: Any) -> list[dict[str, Any]]:
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError as exc:
            raise ValueError("options must be JSON array") from exc
    if not isinstance(options, list):
        raise ValueError("options must be an array")
    out: list[dict[str, Any]] = []
    for index, row in enumerate(options):
        if not isinstance(row, dict):
            raise ValueError(f"options[{index}] must be an object")
        opt_id = str(row.get("id") or "").strip()
        label = str(row.get("label") or "").strip()
        if not opt_id or not label:
            raise ValueError(f"options[{index}] requires id and label")
        entry: dict[str, Any] = {"id": opt_id, "label": label}
        desc = row.get("description")
        if desc:
            entry["description"] = str(desc)
        out.append(entry)
    return out


@mcp.tool()
def ask_human(
    question: str,
    options: list[dict[str, Any]] | str,
    multiSelect: bool = False,
    context_ref: str | None = None,
) -> dict[str, Any]:
    """Human에게 구조화된 방향 결정을 요청한다. prose 질문 금지 — 이 tool만 사용."""
    from agent_lab.human_inbox import create_mcp_question_and_wait

    folder = _session_folder()
    normalized = _normalize_options(options)
    return create_mcp_question_and_wait(
        folder,
        question=str(question or "").strip(),
        options=normalized,
        multi_select=bool(multiSelect),
        context_ref=context_ref,
    )


@mcp.tool()
def propose_build(
    summary: str,
    action_ref: str,
    risks: list[str] | None = None,
    estimated_scope: str | None = None,
) -> dict[str, Any]:
    """Plan phase 완료 후 implement 전 Human GO를 요청한다 (Cursor Build 대응)."""
    from agent_lab.human_inbox import create_mcp_build_and_wait

    folder = _session_folder()
    text = str(summary or "").strip()
    if estimated_scope:
        text = f"{text}\n\nScope: {estimated_scope.strip()}"
    return create_mcp_build_and_wait(
        folder,
        summary=text,
        action_ref=str(action_ref or "").strip(),
        risks=[str(r) for r in (risks or []) if str(r).strip()],
    )


@mcp.tool()
def wisdom_search(query: str, k: int = 3) -> dict[str, Any]:
    """세션 위즈덤(검증·학습·evidence) 검색 — 과거 결론을 재발견해 토론에 인용한다."""
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
