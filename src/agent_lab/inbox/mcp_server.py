"""stdio MCP server — ask_human / propose_build / plan_phase_advance / run_clarity_interview."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel

mcp = FastMCP("agent-lab-inbox")
_logger = logging.getLogger(__name__)


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
        if row.get("recommended"):
            entry["recommended"] = True
        out.append(entry)
    return out


class _AskHumanChoice(BaseModel):
    """Elicitation schema for ``ask_human`` — flat fields only.

    This is a permanent constraint, not a TODO: the MCP elicit schema
    validator (``mcp/server/elicitation.py``) only allows flat
    str/int/float/bool/Optional[...]/list[str] fields, so ``ask_human``'s full
    option shape (id/label/description/recommended badge) cannot be
    represented in an elicit round-trip — only "pick an option id, optionally
    leave a note" survives. The recommended-badge/description UI is only ever
    seen via the Human Inbox web panel (the polling fallback below).
    """

    choice: str
    note: str | None = None


async def _try_elicit_ask_human(
    ctx: Context,
    folder: Path,
    question: str,
    options: list[dict[str, Any]],
    context_ref: str | None,
) -> dict[str, Any] | None:
    """Best-effort MCP elicitation attempt for ``ask_human``.

    Returns ``None`` on any non-accept outcome (client lacks the elicitation
    capability, the client declines/cancels, or the request errors/times
    out) so the caller falls back to the existing
    ``create_mcp_question_and_wait`` poll-based flow unchanged. Never raises.
    """
    from mcp import types as mcp_types
    from mcp.shared.exceptions import McpError

    from agent_lab.human_inbox import (
        build_ask_human_tool_result,
        create_inbox_item,
        resolve_inbox_item,
    )

    try:
        supports = ctx.session.check_client_capability(
            mcp_types.ClientCapabilities(elicitation=mcp_types.ElicitationCapability())
        )
    except Exception:
        supports = False
    if not supports:
        _logger.info("ask_human: client does not declare elicitation support — using poll fallback")
        return None

    option_ids = {str(o.get("id")) for o in options}
    prompt = question + "\n\n" + "\n".join(f"- {o['id']}: {o['label']}" for o in options)
    try:
        result = await ctx.elicit(prompt, _AskHumanChoice)
    except McpError:
        _logger.info("ask_human: elicitation request failed — using poll fallback", exc_info=True)
        return None
    except Exception:
        _logger.info("ask_human: elicitation raised unexpectedly — using poll fallback", exc_info=True)
        return None

    from mcp.server.elicitation import AcceptedElicitation

    if not isinstance(result, AcceptedElicitation):
        action = getattr(result, "action", "declined")
        _logger.info("ask_human: client %s the elicitation — using poll fallback", action)
        return None

    choice = str(result.data.choice).strip()
    if choice not in option_ids:
        _logger.info("ask_human: elicited choice %r not among option ids — using poll fallback", choice)
        return None

    item = create_inbox_item(
        folder,
        kind="question",
        source="mcp_ask_human",
        prompt=question,
        options=options,
        multi_select=False,
        context_ref=context_ref,
    )
    resolved = resolve_inbox_item(
        folder,
        item["id"],
        selected=[choice],
        note=(result.data.note or None),
        actor="human",
    )
    _logger.info("ask_human: resolved via MCP elicitation (item=%s)", item["id"])
    return build_ask_human_tool_result(resolved)


@mcp.tool()
async def ask_human(
    question: str,
    options: list[dict[str, Any]] | str,
    multiSelect: bool = False,
    context_ref: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Human에게 구조화된 방향 결정을 요청한다. prose 질문 금지 — 이 tool만 사용.

    Each option: ``{"id", "label", "description"?, "recommended"?}``.
    추천하는 선택지에 ``"recommended": true``를 주면 Human에게 추천 배지로 표시된다.
    """
    from agent_lab.human_inbox import create_mcp_question_and_wait
    from agent_lab.inbox.mcp_policy import enforce_mcp_ask_human_policy

    folder = _session_folder()
    normalized = _normalize_options(options)
    question_norm = str(question or "").strip()

    # Policy runs regardless of whether the elicit attempt below is taken —
    # never let it be bypassed by the elicitation shortcut.
    enforce_mcp_ask_human_policy(folder, caller_agent=None, policy_lane=None)

    if not multiSelect and len(normalized) >= 2 and ctx is not None:
        elicited = await _try_elicit_ask_human(ctx, folder, question_norm, normalized, context_ref)
        if elicited is not None:
            return elicited

    return create_mcp_question_and_wait(
        folder,
        question=question_norm,
        options=normalized,
        multi_select=bool(multiSelect),
        context_ref=context_ref,
    )


def _propose_build_impl(
    summary: str,
    action_ref: str,
    risks: list[str] | None = None,
    estimated_scope: str | None = None,
) -> dict[str, Any]:
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
def propose_build(
    summary: str,
    action_ref: str,
    risks: list[str] | None = None,
    estimated_scope: str | None = None,
) -> dict[str, Any]:
    """Plan phase 완료 후 implement 전 Human GO를 요청한다 (Cursor Build 대응)."""
    return _propose_build_impl(summary, action_ref, risks=risks, estimated_scope=estimated_scope)


@mcp.tool()
def execute_propose(
    summary: str,
    action_ref: str,
    risks: list[str] | None = None,
    estimated_scope: str | None = None,
) -> dict[str, Any]:
    """GJC-style alias for propose_build — Human GO before implement."""
    return _propose_build_impl(summary, action_ref, risks=risks, estimated_scope=estimated_scope)


@mcp.tool()
def plan_phase_advance(
    target_phase: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Advance plan_workflow FSM toward Human approval (gate owner only).

    Allowed targets: CLARIFY, DRAFT, PEER_REVIEW, REFINE, HUMAN_PENDING.
    APPROVED requires Human plan approve API — not this tool.
    """
    from agent_lab.plan.workflow import mcp_advance_plan_workflow_phase

    folder = _session_folder()
    return mcp_advance_plan_workflow_phase(
        folder,
        target_phase=target_phase,
        reason=reason,
    )


@mcp.tool()
def run_clarity_interview() -> dict[str, Any]:
    """Score 4-axis clarity panel and surface clarifier questions (CLARIFY gate owner only)."""
    from agent_lab.plan.workflow import mcp_run_clarity_interview

    folder = _session_folder()
    return mcp_run_clarity_interview(folder)


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
