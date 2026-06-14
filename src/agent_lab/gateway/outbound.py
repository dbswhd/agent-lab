"""Outbound webhook delivery — Gateway Phase B."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from agent_lab.gateway.config import load_gateway_config

_log = logging.getLogger(__name__)

OutboundEvent = str


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sign_body(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def deliver_outbound_event(
    event: OutboundEvent,
    payload: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST JSON to configured webhook URLs. Best-effort; never raises."""
    cfg = config if config is not None else load_gateway_config()
    outbound = dict(cfg.get("outbound") or {})
    if not outbound.get("enabled"):
        return {"ok": True, "skipped": True, "reason": "outbound_disabled"}
    allowed = {str(e) for e in (outbound.get("events") or [])}
    if event != "test_ping" and allowed and event not in allowed:
        return {"ok": True, "skipped": True, "reason": "event_not_subscribed", "event": event}
    urls = [str(u).strip() for u in (outbound.get("urls") or []) if str(u).strip()]
    if not urls:
        return {"ok": True, "skipped": True, "reason": "no_urls"}

    envelope = {
        "event": event,
        "ts": _now_iso(),
        "payload": payload,
    }
    body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    secret = str(outbound.get("secret") or "")
    timeout = max(1, min(int(outbound.get("timeout_s") or 5), 30))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "agent-lab-gateway/1",
    }
    if secret.strip():
        headers["X-Agent-Lab-Signature"] = _sign_body(secret, body)

    results: list[dict[str, Any]] = []
    for url in urls:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                results.append({"url": url, "ok": 200 <= resp.status < 300, "status": resp.status})
        except urllib.error.HTTPError as exc:
            results.append({"url": url, "ok": False, "status": exc.code, "error": str(exc)})
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            results.append({"url": url, "ok": False, "error": str(exc)})
            _log.warning("gateway outbound failed url=%s err=%s", url, exc)

    ok = all(r.get("ok") for r in results) if results else False
    return {"ok": ok, "skipped": False, "event": event, "results": results}


def ping_outbound() -> dict[str, Any]:
    return deliver_outbound_event("test_ping", {"message": "agent-lab gateway ping"})
