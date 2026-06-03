from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from agent_lab.agent_health import build_health_payload, reconnect_cursor_bridge
from agent_lab.agent_preflight import build_agent_preflight
from agent_lab.api_diagnostics import build_diagnostics_payload
from agent_lab.session import SESSIONS_DIR
from agent_lab.session_setup import session_setup_options

from app.server.deps import room_session_context

router = APIRouter(prefix="/api")


@router.get("/session-setup/options")
def get_session_setup_options() -> dict[str, Any]:
    return session_setup_options()


@router.get("/health")
def health(
    probe_bridge: bool = False,
    probe_preflight: bool = False,
    session_id: str | None = None,
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
