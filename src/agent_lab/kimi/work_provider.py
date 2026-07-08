"""Kimi Work peer provider — Work quota via daimon Control WS."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from agent_lab.env_flags import env_bool
from agent_lab.kimi.control_client import (
    KimiWorkBridgeUnavailable,
    is_share_configured,
    send_turn,
)
from agent_lab.kimi.work_push_mapper import KimiWorkPushMapper
from agent_lab.agents.prompts import KIMI_WORK_ROOM

DEFAULT_MODEL = "k2p6"


def kimi_work_model() -> str:
    return (os.getenv("AGENT_LAB_KIMI_WORK_MODEL") or "").strip() or DEFAULT_MODEL


def model_label() -> str:
    return f"kimi-work:{kimi_work_model()}"


def _mock_enabled() -> bool:
    return env_bool("AGENT_LAB_MOCK_AGENTS")


def is_configured() -> bool:
    if _mock_enabled():
        return True
    return is_share_configured()


def is_available() -> bool:
    if _mock_enabled():
        return True
    # Bridge liveness is checked at turn time / health probe — avoid spawn+WS probe on roster.
    return is_configured()


def respond(
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
    on_activity: Callable[[str], None] | None = None,
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None = None,
    session_folder: str | Path | None = None,
    request_structured_envelope: bool = False,
    inbox_mcp: bool = False,
    **_kwargs: Any,
) -> str:
    folder = session_folder
    if folder is None:
        raise KimiWorkBridgeUnavailable(
            "Kimi Work requires session_folder for conversation mapping",
            code="kimi_work_session_required",
        )
    folder_path = Path(folder)

    from agent_lab.run.meta import read_run_meta
    from agent_lab.room.preset import is_fast_room_session
    from agent_lab.cursor.inbox_mcp import discuss_inbox_mcp_enabled

    run_meta = read_run_meta(folder_path)
    use_inbox_mcp = inbox_mcp and discuss_inbox_mcp_enabled(
        run_meta,
        agent_id="kimi_work",
    )

    base_system = (system or KIMI_WORK_ROOM).strip()
    if is_fast_room_session(run_meta):
        base_system = (
            f"{base_system}\n\n"
            "[Fast preset — solo turn]\n"
            "- Answer the Human directly in one reply. No peer ENDORSE/AMEND, no `[PROPOSED:]` plan tables, "
            "no waiting for colleagues.\n"
            "- Verify with tools first, then summarize findings and a clear recommendation."
        )
    if request_structured_envelope:
        from agent_lab.agent.envelope import ENVELOPE_FORMAT_GUIDANCE_SHORT
        from agent_lab.structured_envelope_adapter import structured_envelope_system_addon

        addon = structured_envelope_system_addon(compact=True)
        mirror = f"{ENVELOPE_FORMAT_GUIDANCE_SHORT}\n(Context: Loop consensus envelope)"
        base_system = f"{base_system}\n\n{addon}\n\n{mirror}"
    if use_inbox_mcp:
        from agent_lab.kimi.work_inbox_bridge import inbox_mcp_system_addon

        inbox_addon = inbox_mcp_system_addon(compact=True)
        base_system = f"{base_system}\n\n{inbox_addon}" if base_system else inbox_addon
    system = base_system
    if on_activity:
        on_activity(f"[net] {model_label()} daimon/conversations.send")

    from agent_lab.run.control import check_cancelled

    check_cancelled()

    from agent_lab.kimi.work_session import ensure_kimi_work_session
    from agent_lab.kimi.work_workspace import resolve_workspace_path

    workspace = resolve_workspace_path(permissions, folder_path)
    conversation_key = ensure_kimi_work_session(
        folder_path,
        workspace_path=workspace,
        title=folder_path.name,
    )
    if on_activity:
        from agent_lab.room.sse_stream import format_tool_activity_line

        on_activity(format_tool_activity_line(tool="workspace", args=str(workspace)))

    # Per-call instance — Room dispatches agents on a ThreadPoolExecutor, and a
    # module-level singleton here would let concurrent Kimi Work turns (across
    # sessions, or overlapping retries) interleave snapshots into the same
    # cumulative-text buffers, corrupting each other's streamed reply/thinking.
    push_mapper = KimiWorkPushMapper()

    def _on_push(method: str, payload: dict[str, Any]) -> None:
        push_mapper.emit_push(method, payload, on_bridge_event)

    push_handler: Callable[[str, dict[str, Any]], None] = _on_push
    if use_inbox_mcp:
        from agent_lab.kimi.work_inbox_bridge import KimiWorkInboxBridge

        inbox_bridge = KimiWorkInboxBridge(
            session_folder=folder_path,
            conversation_key=conversation_key,
            on_bridge_event=on_bridge_event,
            on_activity=on_activity,
        )
        push_handler = inbox_bridge.wrap_push_handler(_on_push)

    completed: list[str] = []

    def _capture_push(method: str, payload: dict[str, Any]) -> None:
        if method == "conversations.message.complete":
            from agent_lab.kimi.work_push_payload import assistant_reply_text

            body = assistant_reply_text(payload) or str(payload.get("text") or "").strip()
            if body:
                completed.append(body)
        push_handler(method, payload)

    if use_inbox_mcp:
        inbox_bridge.set_submit_push(_capture_push)

    body = send_turn(
        conversation_key=conversation_key,
        text=user,
        system=system,
        on_push=_capture_push,
    )
    return body or (completed[-1] if completed else "")
