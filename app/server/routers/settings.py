"""Settings API — user credentials and env-backed secrets."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

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


@router.get("/settings/credentials")
def get_credentials() -> dict[str, Any]:
    return public_credentials_payload()


@router.put("/settings/credentials")
def put_credentials(body: CredentialsPatchRequest) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    merged = patch_from_request(payload)
    path = save_credentials(merged)
    result = public_credentials_payload()
    result["saved"] = True
    result["path"] = str(path)
    return result
