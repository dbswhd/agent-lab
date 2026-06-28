"""Slash commands and agent plugin inventory API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_lab.command_registry import ACCOUNT_COMMAND_IDS, invoke_tool, list_commands
from agent_lab.plugin_discovery import (
    discover_plugins,
    merge_session_allowlist,
    patch_agent_plugins,
)
from agent_lab.runtime.external_runner import patch_external_tools_allowlist
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.workspace.roots import discuss_primary_workspace
from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class AgentPluginsPatchRequest(BaseModel):
    agent: str = Field(..., min_length=1)
    enabled: list[str] = Field(default_factory=list)


class CommandRunRequest(BaseModel):
    command_id: str = Field(..., min_length=1)
    args: str = ""
    confirm: bool = False


class ExternalToolsPatchRequest(BaseModel):
    enabled: list[str] = Field(default_factory=list)


def _workspace_for_session(folder) -> Path:
    run = read_run_meta(folder)
    perms = run.get("permissions") if isinstance(run.get("permissions"), dict) else {}
    return Path(discuss_primary_workspace(perms))


@router.get("/commands")
def get_commands(session_id: str | None = None) -> dict[str, Any]:
    folder = session_folder_or_404(session_id) if session_id else None
    ws = (
        _workspace_for_session(folder)
        if folder
        else Path(os.getenv("AGENT_LAB_ROOT", Path(__file__).resolve().parents[3]))
    )
    payload = list_commands(folder, workspace=ws)
    return {"ok": True, **payload}


@router.get("/agents/plugins")
def get_agent_plugins(session_id: str | None = None) -> dict[str, Any]:
    folder = session_folder_or_404(session_id) if session_id else None
    ws = (
        _workspace_for_session(folder)
        if folder
        else Path(os.getenv("AGENT_LAB_ROOT", Path(__file__).resolve().parents[3]))
    )
    discovery = discover_plugins(ws)
    run = read_run_meta(folder) if folder else {}
    allowlist = merge_session_allowlist(run, discovery.get("plugins") or [])
    return {
        "ok": True,
        "workspace": discovery.get("workspace"),
        "mock": discovery.get("mock", False),
        "agents": discovery.get("agents"),
        "plugins": discovery.get("plugins"),
        "allowlist": allowlist,
    }


@router.patch("/sessions/{session_id}/agent-plugins")
def patch_session_agent_plugins(
    session_id: str,
    body: AgentPluginsPatchRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    agent = body.agent.strip().lower()
    if agent not in {"cursor", "codex", "claude"}:
        raise HTTPException(status_code=422, detail="agent must be cursor, codex, or claude")

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        return patch_agent_plugins(run, agent, body.enabled)

    patch_run_meta(folder, _patch)
    ws = _workspace_for_session(folder)
    catalog = list_commands(folder, workspace=ws)
    return {
        "ok": True,
        "agent": agent,
        "enabled": body.enabled,
        "allowlist": catalog.get("allowlist"),
    }


@router.post("/commands/run")
def post_global_command_run(body: CommandRunRequest) -> dict[str, Any]:
    """Run account slash commands before a session exists (New session composer)."""
    command_id = body.command_id.strip().lower()
    if command_id not in ACCOUNT_COMMAND_IDS:
        raise HTTPException(status_code=422, detail="command requires an active session")
    ws = Path(os.getenv("AGENT_LAB_ROOT", Path(__file__).resolve().parents[3]))
    tr = invoke_tool(
        None,
        command_id,
        args=body.args,
        confirm=body.confirm,
        workspace=ws,
    )
    if not tr.ok:
        detail = tr.error
        if not detail and isinstance(tr.raw.get("result"), dict):
            detail = tr.raw["result"].get("detail")
        raise HTTPException(status_code=409, detail=detail or "command failed")
    return {"ok": True, **tr.raw, "envelope": tr.to_dict()}


@router.post("/sessions/{session_id}/commands/run")
def post_session_command_run(
    session_id: str,
    body: CommandRunRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    ws = _workspace_for_session(folder)

    tr = invoke_tool(
        folder,
        body.command_id,
        args=body.args,
        confirm=body.confirm,
        workspace=ws,
    )
    if not tr.ok:
        detail = tr.error
        if not detail and isinstance(tr.raw.get("result"), dict):
            detail = tr.raw["result"].get("detail")
        raise HTTPException(status_code=409, detail=detail or "command failed")
    return {"ok": True, **tr.raw, "envelope": tr.to_dict()}


@router.patch("/sessions/{session_id}/external-tools")
def patch_session_external_tools(
    session_id: str,
    body: ExternalToolsPatchRequest,
) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    ws = _workspace_for_session(folder)

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        return patch_external_tools_allowlist(run, body.enabled)

    patch_run_meta(folder, _patch)
    catalog = list_commands(folder, workspace=ws)
    return {
        "ok": True,
        "enabled": body.enabled,
        "external_tools": catalog.get("external_tools"),
    }
