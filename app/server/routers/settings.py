"""Settings API — user credentials and env-backed secrets."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_lab.codex_oauth import (
    capture_profile,
    clear_profile,
    probe_captured_profiles,
    public_codex_oauth_payload,
    save_meta,
)
from agent_lab.credential_store import (
    patch_from_request,
    public_credentials_payload,
    save_credentials,
)

router = APIRouter(prefix="/api")


class CredentialSlot(BaseModel):
    primary: str = ""
    fallback: str = ""
    primary_label: str = Field(default="", max_length=40)
    fallback_label: str = Field(default="", max_length=40)


class CredentialsPatchRequest(BaseModel):
    cursor: CredentialSlot | None = None
    claude: CredentialSlot | None = None
    codex: CredentialSlot | None = None


class CodexOAuthCaptureRequest(BaseModel):
    slot: Literal["primary", "fallback"]
    label: str = Field(default="", max_length=40)


class CodexOAuthMetaRequest(BaseModel):
    primary_label: str = Field(default="", max_length=40)
    fallback_label: str = Field(default="", max_length=40)


@router.get("/settings/credentials")
def get_credentials() -> dict[str, Any]:
    return public_credentials_payload()


@router.put("/settings/credentials")
def put_credentials(body: CredentialsPatchRequest) -> dict[str, Any]:
    # Dynamic resilient room: credential writes move to slash commands (/login,
    # /accounts). When AGENT_LAB_DYNAMIC_ROOM is on, the Settings PUT is read-only
    # status; OFF-parity keeps the legacy write path byte-stable.
    from agent_lab.agent_roster import dynamic_room_enabled

    if dynamic_room_enabled():
        result = public_credentials_payload()
        result["saved"] = False
        result["read_only"] = True
        result["note"] = "Credential writes are managed via slash commands (/login, /accounts)."
        return result
    payload = body.model_dump(exclude_none=True)
    merged = patch_from_request(payload)
    path = save_credentials(merged)
    result = public_credentials_payload()
    result["saved"] = True
    result["path"] = str(path)
    return result


@router.get("/settings/codex-oauth")
def get_codex_oauth() -> dict[str, Any]:
    return public_codex_oauth_payload()


@router.put("/settings/codex-oauth/meta")
def put_codex_oauth_meta(body: CodexOAuthMetaRequest) -> dict[str, Any]:
    meta = save_meta({k: v for k, v in body.model_dump().items() if v and str(v).strip()})
    payload = public_codex_oauth_payload()
    payload["meta"] = meta
    return payload


@router.post("/settings/codex-oauth/capture")
def post_codex_oauth_capture(body: CodexOAuthCaptureRequest) -> dict[str, Any]:
    try:
        result = capture_profile(body.slot, label=body.label or None)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    payload = public_codex_oauth_payload()
    payload["capture"] = result
    return payload


@router.delete("/settings/codex-oauth/{slot}")
def delete_codex_oauth_slot(slot: Literal["primary", "fallback"]) -> dict[str, Any]:
    clear_profile(slot)
    return public_codex_oauth_payload()


@router.post("/settings/codex-oauth/probe")
def post_codex_oauth_probe() -> dict[str, Any]:
    profiles = probe_captured_profiles()
    payload = public_codex_oauth_payload()
    payload["profiles"] = profiles
    payload["probe_ok"] = bool(profiles) and all(p.get("ok") for p in profiles)
    return payload
