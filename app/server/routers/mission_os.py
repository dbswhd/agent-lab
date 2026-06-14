"""Mission OS API — templates, schedules, gateway settings, daemon health."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agent_lab.daemon_state import public_daemon_payload
from agent_lab.gateway.config import (
    load_gateway_config,
    public_gateway_payload,
    save_gateway_config,
)
from agent_lab.gateway.outbound import ping_outbound
from agent_lab.mission_scheduler import scheduler_tick
from agent_lab.mission_templates import (
    get_template_detail,
    init_plan_workflow_from_template,
    list_mission_templates,
)
from agent_lab.run_meta import patch_run_meta, read_run_meta

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class GatewayOutboundPatch(BaseModel):
    enabled: bool | None = None
    urls: list[str] | None = None
    events: list[str] | None = None
    secret: str | None = None
    timeout_s: int | None = Field(default=None, ge=1, le=30)


class GatewayTelegramPatch(BaseModel):
    enabled: bool | None = None
    bot_token: str | None = None
    allowed_chat_ids: list[int] | None = None


class GatewayDiscordPatch(BaseModel):
    webhook_url: str | None = None
    allowed_channel_ids: list[str] | None = None


class GatewaySlackPatch(BaseModel):
    enabled: bool | None = None
    webhook_url: str | None = None
    bot_token: str | None = None
    signing_secret: str | None = None
    allowed_channel_ids: list[str] | None = None
    allow_ingress_without_webhook: bool | None = None


class GatewayHybridPatch(BaseModel):
    enabled: bool | None = None
    relay_url: str | None = None
    relay_secret: str | None = None
    relay_when: str | None = None
    timeout_s: int | None = Field(default=None, ge=1, le=30)
    wake_url: str | None = None
    wake_secret: str | None = None
    wake_enabled: bool | None = None
    wake_events: list[str] | None = None


class GatewayAdaptersPatch(BaseModel):
    enabled: list[str] | None = None


class GatewayPatchRequest(BaseModel):
    outbound: GatewayOutboundPatch | None = None
    telegram: GatewayTelegramPatch | None = None
    discord: GatewayDiscordPatch | None = None
    slack: GatewaySlackPatch | None = None
    hybrid: GatewayHybridPatch | None = None
    adapters: GatewayAdaptersPatch | None = None


class ScheduleEntry(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    cron: str = Field(min_length=1, max_length=120)
    tz: str = Field(default="UTC", max_length=64)
    template_id: str | None = Field(default=None, max_length=80)
    gate_profile: Literal["dev", "assistant"] = "assistant"
    sandbox: bool = True
    enabled: bool = True
    notify: dict[str, bool] | None = None


class SchedulesPatchRequest(BaseModel):
    schedules: list[ScheduleEntry]


class TemplateApplyRequest(BaseModel):
    template_id: str = Field(min_length=1, max_length=80)


@router.get("/settings/gateway")
def get_gateway_settings() -> dict[str, Any]:
    from agent_lab.gateway.adapters import public_adapters_payload

    cfg = load_gateway_config()
    return {**public_gateway_payload(cfg), **public_adapters_payload(cfg)}


@router.patch("/settings/gateway")
def patch_gateway_settings(body: GatewayPatchRequest) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if body.outbound is not None:
        patch["outbound"] = body.outbound.model_dump(exclude_none=True)
    if body.telegram is not None:
        patch["telegram"] = body.telegram.model_dump(exclude_none=True)
    if body.discord is not None:
        patch["discord"] = body.discord.model_dump(exclude_none=True)
    if body.slack is not None:
        patch["slack"] = body.slack.model_dump(exclude_none=True)
    if body.hybrid is not None:
        patch["hybrid"] = body.hybrid.model_dump(exclude_none=True)
    if body.adapters is not None:
        patch["adapters"] = body.adapters.model_dump(exclude_none=True)
    cfg = save_gateway_config(patch)
    from agent_lab.gateway.adapters import public_adapters_payload

    return {"ok": True, **public_gateway_payload(cfg), **public_adapters_payload(cfg)}


@router.post("/settings/gateway/ping")
def post_gateway_ping() -> dict[str, Any]:
    result = ping_outbound()
    return {"ok": True, **result}


@router.get("/health/daemon")
def health_daemon() -> dict[str, Any]:
    from agent_lab.gateway.adapters import public_adapters_payload

    cfg = load_gateway_config()
    payload = public_daemon_payload()
    payload["ok"] = True
    payload["gateway"] = {**public_gateway_payload(cfg), **public_adapters_payload(cfg)}
    return payload


@router.get("/templates")
def list_templates() -> dict[str, Any]:
    return {"templates": list_mission_templates()}


@router.get("/templates/{template_id}")
def template_detail(template_id: str) -> dict[str, Any]:
    try:
        detail = get_template_detail(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return detail


@router.get("/sessions/{session_id}/schedules")
def get_session_schedules(session_id: str) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    run = read_run_meta(folder)
    return {"session_id": session_id, "schedules": list(run.get("schedules") or [])}


@router.patch("/sessions/{session_id}/schedules")
def patch_session_schedules(session_id: str, body: SchedulesPatchRequest) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        run["schedules"] = [entry.model_dump() for entry in body.schedules]
        return run

    updated = patch_run_meta(folder, _patch)
    return {"ok": True, "session_id": session_id, "schedules": updated.get("schedules") or []}


@router.post("/sessions/{session_id}/schedules/{schedule_id}/approve")
def approve_session_schedule(session_id: str, schedule_id: str) -> dict[str, Any]:
    """Gate 5-A — Human one-time schedule sign-off."""
    folder = session_folder_or_404(session_id)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    found = False

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        nonlocal found
        schedules = list(run.get("schedules") or [])
        for entry in schedules:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("id") or "") != schedule_id:
                continue
            entry["pre_approved_at"] = now
            entry["pre_approved_by"] = "human"
            found = True
        run["schedules"] = schedules
        return run

    updated = patch_run_meta(folder, _patch)
    if not found:
        raise HTTPException(status_code=404, detail="schedule not found")
    return {
        "ok": True,
        "session_id": session_id,
        "schedule_id": schedule_id,
        "schedules": updated.get("schedules") or [],
    }


@router.post("/sessions/{session_id}/templates/apply")
def apply_session_template(session_id: str, body: TemplateApplyRequest) -> dict[str, Any]:
    folder = session_folder_or_404(session_id)
    try:
        result = init_plan_workflow_from_template(folder, body.template_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "session_id": session_id, **result}


@router.post("/mission-scheduler/tick")
def post_mission_scheduler_tick(
    request: Request,
    force: bool = False,
) -> dict[str, Any]:
    """Manual scheduler tick (tests / ops). Optional ``AGENT_LAB_SCHEDULER_HOOK_TOKEN``."""
    import os

    token = (os.getenv("AGENT_LAB_SCHEDULER_HOOK_TOKEN") or "").strip()
    if token:
        header = (request.headers.get("X-Agent-Lab-Scheduler-Token") or "").strip()
        if header != token:
            raise HTTPException(status_code=401, detail="invalid scheduler token")
    return scheduler_tick(force=force)
