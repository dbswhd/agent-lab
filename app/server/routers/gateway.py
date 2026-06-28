"""Gateway ingress — Telegram webhook and inbound hooks."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agent_lab.gateway.adapters import (
    fan_out_gateway_notify,
    process_gateway_ingress,
    public_adapters_payload,
)
from agent_lab.gateway.config import load_gateway_config
from agent_lab.gateway.hybrid_relay import public_hybrid_payload
from agent_lab.gateway.router import public_routes_payload

router = APIRouter(prefix="/api")


class InboundHookBody(BaseModel):
    text: str = Field(default="", max_length=8000)
    payload: dict[str, Any] | None = None


class CliIngressBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = Field(default=None, max_length=120)
    gate_profile: str | None = Field(default=None, max_length=32)


class DiscordIngressBody(BaseModel):
    content: str = Field(default="", max_length=8000)
    channel_id: str | None = Field(default=None, max_length=80)
    interaction: dict[str, Any] | None = None


@router.get("/gateway/routes")
def get_gateway_routes() -> dict[str, Any]:
    return {"ok": True, **public_routes_payload()}


@router.get("/gateway/adapters")
def get_gateway_adapters() -> dict[str, Any]:
    cfg = load_gateway_config()
    return {
        "ok": True,
        **public_adapters_payload(cfg),
        "hybrid": public_hybrid_payload(cfg),
    }


@router.post("/gateway/telegram/webhook")
async def post_telegram_webhook(request: Request) -> dict[str, Any]:
    try:
        update = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid json") from exc
    if not isinstance(update, dict):
        raise HTTPException(status_code=400, detail="update must be object")
    result = process_gateway_ingress("telegram", {"update": update})
    return {"ok": True, **result}


class SlackIngressBody(BaseModel):
    content: str = Field(default="", max_length=8000)
    channel_id: str | None = Field(default=None, max_length=80)
    type: str | None = Field(default=None, max_length=64)
    challenge: str | None = Field(default=None, max_length=256)
    event: dict[str, Any] | None = None


@router.post("/gateway/discord/webhook")
def post_discord_webhook(body: DiscordIngressBody) -> dict[str, Any]:
    result = process_gateway_ingress(
        "discord",
        body.model_dump(exclude_none=True),
    )
    return {"ok": True, **result}


@router.post("/gateway/slack/events")
async def post_slack_events(request: Request) -> dict[str, Any]:
    body_bytes = await request.body()
    headers = {k: v for k, v in request.headers.items()}
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be object")
    payload["_headers"] = headers
    payload["_raw_body"] = body_bytes
    result = process_gateway_ingress("slack", payload)
    if result.get("reason") == "invalid_signature":
        raise HTTPException(status_code=401, detail="invalid slack signature")
    if result.get("challenge"):
        return {"challenge": result["challenge"]}
    return {"ok": True, **result}


@router.post("/gateway/cli")
def post_gateway_cli(body: CliIngressBody) -> dict[str, Any]:
    result = process_gateway_ingress(
        "cli",
        body.model_dump(exclude_none=True),
    )
    return {"ok": True, **result}


@router.post("/hooks/{hook_id}")
def post_inbound_hook(
    hook_id: str,
    request: Request,
    body: InboundHookBody | None = None,
) -> dict[str, Any]:
    """CI / external wake — routes to session via routes.toml."""
    if hook_id == "mission-wake":
        from agent_lab.gateway.hybrid_relay import verify_wake_request
        from agent_lab.mission.scheduler import scheduler_tick

        headers = {k: v for k, v in request.headers.items()}
        if not verify_wake_request(headers, body=b"{}"):
            raise HTTPException(status_code=401, detail="invalid wake credentials")
        tick = scheduler_tick(force=True)
        return {"ok": True, "wake": True, **tick}
    payload = body or InboundHookBody()
    result = process_gateway_ingress(
        "webhook",
        {
            "hook_id": hook_id,
            "text": payload.text,
            "payload": payload.payload,
        },
    )
    return {"ok": True, "hook_id": hook_id, **result}


@router.post("/gateway/notify/test")
def post_gateway_notify_test() -> dict[str, Any]:
    return fan_out_gateway_notify(
        "test_ping",
        {"message": "agent-lab gateway adapter fan-out test"},
    )
