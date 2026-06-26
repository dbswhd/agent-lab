from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from agent_lab.agent_health import (
    build_health_payload,
    reconnect_claude_auth,
    reconnect_cursor_bridge,
    reconnect_kimi_work_bridge,
)
from agent_lab.agent_preflight import build_agent_preflight
from agent_lab.readiness import build_readiness_payload
from agent_lab.api_diagnostics import build_diagnostics_payload
from agent_lab.runtime_flags import build_flags_payload
from agent_lab.run_profile import profile_catalog
from agent_lab.native_folder_picker import pick_folder_native
from agent_lab.session import SESSIONS_DIR
from agent_lab.session_setup import session_setup_options

from app.server.deps import room_session_context
from app.server.health_rate_limit import enforce_health_burst_limit

router = APIRouter(prefix="/api")


class PickFolderBody(BaseModel):
    default_path: str | None = Field(default=None, max_length=4096)
    title: str = Field(default="작업 폴더 선택", max_length=120)


@router.post("/desktop/pick-folder")
def desktop_pick_folder(body: PickFolderBody | None = None) -> dict[str, Any]:
    """Native folder picker for browser dev (macOS Finder via osascript)."""
    payload = body or PickFolderBody()
    available, path = pick_folder_native(
        default_path=payload.default_path,
        title=payload.title,
    )
    if not available:
        return {"available": False, "path": None, "cancelled": False}
    return {"available": True, "path": path, "cancelled": path is None}


@router.get("/session-setup/options")
def get_session_setup_options() -> dict[str, Any]:
    return session_setup_options()


@router.get("/health")
def health(
    probe_bridge: bool = False,
    probe_preflight: bool = False,
    session_id: str | None = None,
    _: None = Depends(enforce_health_burst_limit),
) -> dict[str, Any]:
    run_meta: dict[str, Any] | None = None
    if session_id:
        folder = SESSIONS_DIR / session_id
        if folder.is_dir():
            _plan_md, run_meta = room_session_context(folder)
    return build_health_payload(
        probe_bridge=probe_bridge,
        probe_preflight=probe_preflight,
        run_meta=run_meta,
    )


@router.get("/health/codex-proxy")
def health_codex_proxy() -> dict[str, Any]:
    """Dev-only Codex openai-oauth proxy probe (MB-11)."""
    from agent_lab.runtime.adapters.codex import codex_proxy_enabled, probe_codex_proxy

    payload = probe_codex_proxy()
    return {"ok": True, **payload, "env_enabled": codex_proxy_enabled()}


@router.get("/health/flags")
def health_flags(category: str | None = None) -> dict[str, Any]:
    """AGENT_LAB_* env flag registry with active values (discoverability)."""
    return build_flags_payload(category=category)


@router.get("/profiles")
def run_profiles() -> dict[str, Any]:
    """Run profile catalog — four named flag presets (fast|balanced|thorough|autonomous)."""
    return profile_catalog()


@router.get("/health/readiness")
def health_readiness(
    session_id: str | None = None,
    probe_bridge: bool = True,
    probe_cli: bool = True,
) -> dict[str, Any]:
    """Dry-run readiness — no model calls (MB-9)."""
    return build_readiness_payload(
        session_id=session_id,
        probe_bridge=probe_bridge,
        probe_cli=probe_cli,
    )


@router.get("/agents/preflight")
def agents_preflight() -> dict[str, Any]:
    agents = build_agent_preflight(probe_bridge=True, probe_cli=True)
    return {
        "ok": all(a.get("ready") for a in agents),
        "agents": agents,
    }


@router.get("/diagnostics")
def diagnostics() -> dict[str, Any]:
    return build_diagnostics_payload()


@router.post("/health/reconnect-cursor")
def health_reconnect_cursor() -> dict[str, Any]:
    return reconnect_cursor_bridge()


@router.post("/health/reconnect-claude")
def health_reconnect_claude() -> dict[str, Any]:
    return reconnect_claude_auth()


@router.post("/health/reconnect-kimi-work")
def health_reconnect_kimi_work() -> dict[str, Any]:
    return reconnect_kimi_work_bridge()
