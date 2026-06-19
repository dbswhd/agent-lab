"""Kimi Work peer provider — Work quota via daimon Control WS."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from agent_lab.kimi_control_client import (
    KimiWorkBridgeUnavailable,
    is_share_configured,
    probe_control,
    send_turn,
)
from agent_lab.kimi_work_push_mapper import KimiWorkPushMapper

DEFAULT_MODEL = "k2p6"
_push_mapper = KimiWorkPushMapper()


def kimi_work_model() -> str:
    return (os.getenv("AGENT_LAB_KIMI_WORK_MODEL") or "").strip() or DEFAULT_MODEL


def model_label() -> str:
    return f"kimi-work:{kimi_work_model()}"


def _mock_enabled() -> bool:
    return os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes", "on"}


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
    **_kwargs: Any,
) -> str:
    if on_activity:
        on_activity(f"[net] {model_label()} daimon/conversations.send")

    folder = session_folder
    if folder is None:
        raise KimiWorkBridgeUnavailable(
            "Kimi Work requires session_folder for conversation mapping",
            code="kimi_work_session_required",
        )

    from agent_lab.kimi_work_session import get_or_create_conversation
    from agent_lab.kimi_work_workspace import ensure_workspace_bound, resolve_workspace_path

    workspace = resolve_workspace_path(permissions, folder)
    ensure_workspace_bound(folder, workspace)
    if on_activity:
        from agent_lab.room_sse_stream import format_tool_activity_line

        on_activity(format_tool_activity_line(tool="workspace", args=str(workspace)))

    conversation_key = get_or_create_conversation(folder, title=Path(str(folder)).name)

    _push_mapper.reset()

    def _on_push(method: str, payload: dict[str, Any]) -> None:
        _push_mapper.emit_push(method, payload, on_bridge_event)

    return send_turn(
        conversation_key=conversation_key,
        text=user,
        system=system,
        on_push=_on_push,
    )
