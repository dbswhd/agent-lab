"""N9 — Oracle verification audit headers and response extensions."""

from __future__ import annotations

import uuid
from typing import Any


def new_request_id(prefix: str = "verify") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def oracle_audit_headers(
    *,
    service: str,
    request_id: str,
    verdict: str,
    risk_level: str = "",
    oracle_mode: str = "mock",
    session_id: str | None = None,
) -> dict[str, str]:
    headers = {
        "X-AgentLab-Service": service,
        "X-AgentLab-Request-Id": request_id,
        "X-AgentLab-Oracle-Verdict": verdict or "unknown",
        "X-AgentLab-Oracle-Mode": oracle_mode,
    }
    if risk_level:
        headers["X-AgentLab-Risk-Level"] = risk_level
    if session_id:
        headers["X-AgentLab-RunId"] = session_id
    return headers


def agentlab_extension(
    *,
    service: str,
    request_id: str,
    oracle_mode: str,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "service": service,
        "request_id": request_id,
        "oracle_mode": oracle_mode,
    }
    if session_id:
        block["session_id"] = session_id
    if extra:
        block.update(extra)
    return block
