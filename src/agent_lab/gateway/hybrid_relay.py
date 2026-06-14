"""Hybrid cloud notify relay when local daemon is offline."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from agent_lab.daemon_state import load_daemon_state
from agent_lab.gateway.config import load_gateway_config
from agent_lab.gateway.outbound import _sign_body


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hybrid_cfg(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("hybrid") or {})


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def daemon_online(*, stale_s: int | None = None) -> bool:
    """True when local mission daemon recently ticked or pid is alive."""
    max_stale = stale_s
    if max_stale is None:
        max_stale = int(os.getenv("AGENT_LAB_DAEMON_STALE_S", "180"))
    state = load_daemon_state()
    pid = state.get("pid")
    if isinstance(pid, int) and _pid_alive(pid):
        return True
    if isinstance(pid, str) and str(pid).isdigit() and _pid_alive(int(pid)):
        return True
    last = _parse_iso(str(state.get("last_scheduler_tick_at") or ""))
    if last is None:
        last = _parse_iso(str(state.get("started_at") or ""))
    if last is None:
        return False
    age = (datetime.now(timezone.utc) - last.astimezone(timezone.utc)).total_seconds()
    return age <= max(30, max_stale)


def public_hybrid_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config if config is not None else load_gateway_config()
    hybrid = _hybrid_cfg(cfg)
    secret = str(hybrid.get("relay_secret") or "")
    return {
        "enabled": bool(hybrid.get("enabled")),
        "relay_url_set": bool(str(hybrid.get("relay_url") or "").strip()),
        "relay_secret_set": bool(secret.strip()),
        "relay_when": str(hybrid.get("relay_when") or "daemon_offline"),
        "daemon_online": daemon_online(),
    }


def deliver_hybrid_relay(
    event: str,
    payload: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config if config is not None else load_gateway_config()
    hybrid = _hybrid_cfg(cfg)
    if not hybrid.get("enabled"):
        return {"ok": True, "skipped": True, "reason": "hybrid_disabled"}
    url = str(hybrid.get("relay_url") or "").strip()
    if not url:
        return {"ok": True, "skipped": True, "reason": "no_relay_url"}

    envelope = {
        "event": event,
        "ts": _now_iso(),
        "payload": payload,
        "source": "agent-lab-hybrid-relay",
        "daemon_online": daemon_online(),
    }
    body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "agent-lab-gateway/1",
    }
    secret = str(hybrid.get("relay_secret") or "")
    if secret.strip():
        headers["X-Agent-Lab-Signature"] = _sign_body(secret, body)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=max(1, int(hybrid.get("timeout_s") or 8))) as resp:
            return {
                "ok": 200 <= resp.status < 300,
                "skipped": False,
                "status": resp.status,
                "url": url,
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "skipped": False, "status": exc.code, "error": str(exc), "url": url}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "skipped": False, "error": str(exc), "url": url}


def maybe_deliver_hybrid_relay(
    event: str,
    payload: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config if config is not None else load_gateway_config()
    hybrid = _hybrid_cfg(cfg)
    if not hybrid.get("enabled"):
        return {"ok": True, "skipped": True, "reason": "hybrid_disabled"}
    when = str(hybrid.get("relay_when") or "daemon_offline")
    if when == "daemon_offline" and daemon_online():
        return {"ok": True, "skipped": True, "reason": "daemon_online"}
    return deliver_hybrid_relay(event, payload, config=cfg)
