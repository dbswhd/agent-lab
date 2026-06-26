"""Agent Lab Human Inbox bridge for Kimi Work Loop (phase 2).

When ``inbox_mcp=True``, intercept daimon tool-call pushes for ``ask_human`` /
``propose_build`` (or ``inbox.askHuman`` / ``inbox.proposeBuild``), block on
``human_inbox`` until the Human resolves, then submit the tool result back to
daimon via ``conversations.submitToolResult`` (with ``conversations.send`` fallback).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from agent_lab.kimi_work_push_payload import push_message_parts

BridgeEmit = Callable[[str, dict[str, Any]], None]
PushHandler = Callable[[str, dict[str, Any]], None]

_INBOX_TOOL_ALIASES: dict[str, str] = {
    "ask_human": "ask_human",
    "askhuman": "ask_human",
    "inbox.askhuman": "ask_human",
    "inbox.askHuman": "ask_human",
    "propose_build": "propose_build",
    "proposebuild": "propose_build",
    "inbox.proposebuild": "propose_build",
    "inbox.proposeBuild": "propose_build",
}


def kimi_work_inbox_bridge_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_KIMI_WORK_INBOX_BRIDGE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def kimi_work_inbox_bridge_ready() -> bool:
    """True when the Agent Lab-side inbox bridge can run (phase 2 gate helper)."""
    if not kimi_work_inbox_bridge_enabled():
        return False
    try:
        from agent_lab.human_inbox import create_inbox_item  # noqa: F401
    except ImportError:
        return False
    return True


def inbox_mcp_system_addon(*, compact: bool = False) -> str:
    if compact:
        return (
            "[Human Inbox tools]\n"
            "Direction blockers: call `ask_human` with question + >=2 options (never prose).\n"
            "Build GO: call `propose_build` with summary + action_ref; wait for Human decision."
        )
    return (
        "[Human Inbox — mandatory for direction and GO]\n"
        "- If blocked on direction, call `ask_human` with question + at least 2 options "
        "(never ask in prose).\n"
        "- When ready for implement GO, call `propose_build` with summary + action_ref and "
        "wait for Human decision.\n"
        "- Tool names accepted: ask_human, propose_build (or inbox.askHuman / inbox.proposeBuild)."
    )


def _normalize_tool_name(raw: object) -> str | None:
    key = str(raw or "").strip()
    if not key:
        return None
    canonical = _INBOX_TOOL_ALIASES.get(key) or _INBOX_TOOL_ALIASES.get(key.lower())
    return canonical


def _tool_args(part: dict[str, Any]) -> dict[str, Any]:
    raw = part.get("args")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"raw": raw}
    return {}


def _normalize_options(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("options must be JSON array") from exc
    if not isinstance(raw, list):
        raise ValueError("options must be an array")
    out: list[dict[str, Any]] = []
    for index, row in enumerate(raw):
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


def _execute_inbox_tool(
    folder: Path,
    tool: str,
    args: dict[str, Any],
    *,
    mcp_call_id: str,
) -> dict[str, Any]:
    from agent_lab.human_inbox import create_mcp_build_and_wait, create_mcp_question_and_wait

    if tool == "ask_human":
        return create_mcp_question_and_wait(
            folder,
            question=str(args.get("question") or args.get("prompt") or "").strip(),
            options=_normalize_options(args.get("options")),
            multi_select=bool(args.get("multiSelect") or args.get("multi_select")),
            context_ref=str(args.get("context_ref") or "").strip() or None,
            mcp_call_id=mcp_call_id,
        )
    summary = str(args.get("summary") or args.get("prompt") or "").strip()
    action_ref = str(args.get("action_ref") or args.get("actionRef") or "").strip()
    risks_raw = args.get("risks")
    risks = [str(r) for r in risks_raw] if isinstance(risks_raw, list) else []
    return create_mcp_build_and_wait(
        folder,
        summary=summary,
        action_ref=action_ref,
        risks=risks,
        mcp_call_id=mcp_call_id,
    )


class KimiWorkInboxBridge:
    """Intercept inbox tool-call pushes and fulfill them via Human Inbox."""

    def __init__(
        self,
        *,
        session_folder: str | Path,
        conversation_key: str,
        on_bridge_event: BridgeEmit | None = None,
        on_activity: Callable[[str], None] | None = None,
    ) -> None:
        self._folder = Path(session_folder).expanduser().resolve()
        self._conversation_key = conversation_key
        self._on_bridge_event = on_bridge_event
        self._on_activity = on_activity
        self._handled: set[str] = set()
        self._submit_push: PushHandler | None = None

    def set_submit_push(self, handler: PushHandler) -> None:
        """Push handler for tool-result continuations (should include outer capture/mapper)."""
        self._submit_push = handler

    def wrap_push_handler(self, downstream: PushHandler) -> PushHandler:
        def _handler(method: str, payload: dict[str, Any]) -> None:
            if self._try_handle(method, payload, downstream):
                return
            downstream(method, payload)

        return _handler

    def _try_handle(self, method: str, payload: dict[str, Any], downstream: PushHandler) -> bool:
        if method != "conversations.message.snapshot":
            return False
        parts = push_message_parts(payload)
        if not parts:
            return False
        handled_any = False
        for part in parts:
            if not isinstance(part, dict):
                continue
            kind = str(part.get("kind") or part.get("type") or "").strip()
            if kind != "tool-call":
                continue
            tool = _normalize_tool_name(part.get("toolName") or part.get("name"))
            if tool is None:
                raw_name = str(part.get("toolName") or part.get("name") or "").strip()
                lowered = raw_name.lower()
                if raw_name and any(token in lowered for token in ("ask", "inbox", "human", "propose")):
                    if self._on_activity:
                        self._on_activity("[inbox · expected ask_human]")
                continue
            call_id = str(part.get("toolCallId") or tool).strip()
            if not call_id or call_id in self._handled:
                continue
            if any(
                isinstance(other, dict)
                and str(other.get("kind") or "") == "tool-result"
                and str(other.get("toolCallId") or "") == call_id
                for other in parts
            ):
                continue
            self._handled.add(call_id)
            handled_any = True
            args = _tool_args(part)
            if self._on_bridge_event:
                self._on_bridge_event("tool_start", {"tool": tool, "args": args})
            if self._on_activity:
                from agent_lab.room_sse_stream import format_tool_activity_line

                self._on_activity(format_tool_activity_line(tool=tool, args=json.dumps(args, ensure_ascii=False)[:120]))
            try:
                result = _execute_inbox_tool(self._folder, tool, args, mcp_call_id=call_id)
            except Exception as exc:
                result = {"status": "error", "message": str(exc)[:240]}
            result_text = json.dumps(result, ensure_ascii=False)
            if self._on_bridge_event:
                self._on_bridge_event("tool_output", {"tool": tool, "chunk": result_text})
                self._on_bridge_event("tool_done", {"tool": tool})
            from agent_lab.kimi_control_client import submit_conversation_tool_result

            submit_conversation_tool_result(
                conversation_key=self._conversation_key,
                tool_call_id=call_id,
                result=result,
                on_push=self._submit_push or downstream,
            )
        return handled_any
