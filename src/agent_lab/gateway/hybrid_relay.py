"""Hybrid cloud notify relay when local daemon is offline."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from agent_lab.time_utils import utc_now_iso_seconds as _now_iso, utc_now
from agent_lab.daemon_state import load_daemon_state
from agent_lab.gateway.config import load_gateway_config
from agent_lab.gateway.outbound import _sign_body


_DEFAULT_WAKE_EVENTS = (
    "schedule_tick",
    "merge_ready",
    "auto_merge_blocked",
    "gate_blocked",
)


def _hybrid_cfg(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("hybrid") or {})


def wake_events_for(hybrid: dict[str, Any]) -> list[str]:
    raw = hybrid.get("wake_events")
    if raw is None:
        return list(_DEFAULT_WAKE_EVENTS)
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    return list(_DEFAULT_WAKE_EVENTS)


def should_hybrid_wake(
    hybrid: dict[str, Any],
    *,
    event: str,
    daemon_online: bool,
) -> bool:
    if daemon_online:
        return False
    if hybrid.get("wake_enabled") is False:
        return False
    wake_url = str(hybrid.get("wake_url") or "").strip()
    if not wake_url:
        return False
    return event in wake_events_for(hybrid)


def wake_hint_for_envelope(hybrid: dict[str, Any], *, event: str, online: bool) -> dict[str, Any] | None:
    if not should_hybrid_wake(hybrid, event=event, daemon_online=online):
        return None
    wake_url = str(hybrid.get("wake_url") or "").strip()
    return {
        "attempt": True,
        "url": wake_url,
        "method": "POST",
        "event": event,
    }


def verify_wake_request(
    headers: dict[str, str],
    *,
    body: bytes = b"{}",
    config: dict[str, Any] | None = None,
) -> bool:
    """Authorize cloud wake — scheduler token or hybrid relay HMAC."""
    token = (os.getenv("AGENT_LAB_SCHEDULER_HOOK_TOKEN") or "").strip()
    header_token = str(
        headers.get("X-Agent-Lab-Scheduler-Token") or headers.get("x-agent-lab-scheduler-token") or ""
    ).strip()
    if token:
        return header_token == token

    cfg = config if config is not None else load_gateway_config()
    hybrid = _hybrid_cfg(cfg)
    secret = str(hybrid.get("wake_secret") or hybrid.get("relay_secret") or "").strip()
    if not secret:
        return True
    sig = str(headers.get("X-Agent-Lab-Signature") or headers.get("x-agent-lab-signature") or "").strip()
    if not sig:
        return False
    return _sign_body(secret, body) == sig


def request_scheduler_wake(
    *,
    wake_url: str | None = None,
    scheduler_token: str | None = None,
    config: dict[str, Any] | None = None,
    timeout_s: int | None = None,
) -> dict[str, Any]:
    """POST cloud wake URL (tunnel → local scheduler tick). Used by Worker parity/tests."""
    cfg = config if config is not None else load_gateway_config()
    hybrid = _hybrid_cfg(cfg)
    url = str(wake_url or hybrid.get("wake_url") or "").strip()
    if not url:
        return {"ok": False, "skipped": True, "reason": "no_wake_url"}

    body = b"{}"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "agent-lab-hybrid-wake/1",
    }
    token = (scheduler_token or os.getenv("AGENT_LAB_SCHEDULER_HOOK_TOKEN") or "").strip()
    if token:
        headers["X-Agent-Lab-Scheduler-Token"] = token
    else:
        secret = str(hybrid.get("wake_secret") or hybrid.get("relay_secret") or "").strip()
        if secret:
            headers["X-Agent-Lab-Signature"] = _sign_body(secret, body)

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(
            req,
            timeout=max(1, int(timeout_s or hybrid.get("timeout_s") or 8)),
        ) as resp:
            raw = resp.read().decode("utf-8")
            parsed: dict[str, Any] | None = None
            if raw.strip():
                try:
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        parsed = loaded
                except json.JSONDecodeError:
                    parsed = None
            return {
                "ok": 200 <= resp.status < 300,
                "status": resp.status,
                "url": url,
                "body": parsed,
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": str(exc), "url": url}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": str(exc), "url": url}


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
    age = (utc_now() - last.astimezone(timezone.utc)).total_seconds()
    return age <= max(30, max_stale)


def public_hybrid_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config if config is not None else load_gateway_config()
    hybrid = _hybrid_cfg(cfg)
    secret = str(hybrid.get("relay_secret") or "")
    wake_url = str(hybrid.get("wake_url") or "").strip()
    return {
        "enabled": bool(hybrid.get("enabled")),
        "relay_url_set": bool(str(hybrid.get("relay_url") or "").strip()),
        "relay_secret_set": bool(secret.strip()),
        "relay_when": str(hybrid.get("relay_when") or "daemon_offline"),
        "wake_url_set": bool(wake_url),
        "wake_enabled": hybrid.get("wake_enabled", True) is not False,
        "wake_events": wake_events_for(hybrid),
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

    online = daemon_online()
    envelope: dict[str, Any] = {
        "event": event,
        "ts": _now_iso(),
        "payload": payload,
        "source": "agent-lab-hybrid-relay",
        "daemon_online": online,
    }
    wake = wake_hint_for_envelope(hybrid, event=event, online=online)
    if wake is not None:
        envelope["wake"] = wake
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
