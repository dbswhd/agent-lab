"""External tool runner — opt-in Phase C (H7)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_lab.external_tools import load_external_tools, run_external_tool
from agent_lab.run.meta import read_run_meta
from agent_lab.runtime.boulder import clear_last_failure, record_last_failure


def external_runner_enabled() -> bool:
    return os.getenv("AGENT_LAB_EXTERNAL_TOOLS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def external_tools_allowlist(run: dict[str, Any] | None) -> list[str]:
    if not isinstance(run, dict):
        return []
    block = run.get("external_tools")
    if not isinstance(block, dict):
        return []
    enabled = block.get("enabled")
    if not isinstance(enabled, list):
        return []
    return [str(item).strip() for item in enabled if str(item).strip()]


def patch_external_tools_allowlist(run: dict[str, Any], tool_ids: list[str]) -> dict[str, Any]:
    block = dict(run.get("external_tools") or {})
    block["enabled"] = [str(item).strip() for item in tool_ids if str(item).strip()]
    run["external_tools"] = block
    return run


def external_tool_catalog_row(
    row: dict[str, Any],
    *,
    allowlist: list[str],
) -> dict[str, Any]:
    tool_id = str(row.get("id") or "")
    enabled = False
    disabled_reason: str | None = None
    if not external_runner_enabled():
        disabled_reason = "env_required"
    elif row.get("status") == "stub":
        disabled_reason = "stub"
    elif tool_id not in allowlist:
        disabled_reason = "not_in_session_allowlist"
    else:
        enabled = True
    return {
        **row,
        "enabled": enabled,
        "disabled_reason": disabled_reason,
    }


def run_external_command(
    session_folder: Path,
    tool_id: str,
    *,
    args: str = "",
    confirm: bool = False,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Execute external tool with env + allowlist + human confirm gates."""
    if not external_runner_enabled():
        return {
            "ok": False,
            "detail": "external tools disabled (set AGENT_LAB_EXTERNAL_TOOLS=1)",
            "status": "disabled",
        }

    run = read_run_meta(session_folder)
    allowlist = external_tools_allowlist(run)
    if tool_id not in allowlist:
        return {
            "ok": False,
            "detail": f"tool not allowlisted for session: {tool_id}",
            "status": "not_allowlisted",
        }

    tool_row = next((r for r in load_external_tools() if r.get("id") == tool_id), None)
    if not tool_row:
        return {"ok": False, "detail": f"unknown external tool: {tool_id}"}

    if tool_row.get("status") == "stub" or not tool_row.get("command"):
        return {
            "ok": True,
            "status": "stub",
            "detail": (
                f"{tool_row.get('label')} is registered but has no command. Add command to ~/.agent-lab/tools.yaml"
            ),
        }

    if tool_row.get("requires_human_confirm") and not confirm:
        return {
            "ok": False,
            "status": "pending_human",
            "detail": "Human confirm required — retry with confirm=true",
            "command": tool_row,
        }

    result = run_external_tool(
        tool_id,
        session_folder=session_folder,
        args=args,
        workspace=workspace,
    )
    if result.get("ok"):
        from agent_lab.external_handoff import try_attach_handoff_from_external_result

        handoff = try_attach_handoff_from_external_result(
            session_folder,
            result,
            tool_id=tool_id,
        )
        if handoff:
            result["handoff_attach"] = handoff
        clear_last_failure(session_folder)
    else:
        record_last_failure(
            session_folder,
            lane="control",
            event="external.run.fail",
            reason=str(result.get("stderr") or result.get("detail") or "external tool failed"),
            phase=None,
            recoverable=True,
        )
    return result
