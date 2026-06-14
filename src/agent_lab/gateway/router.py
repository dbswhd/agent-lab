"""Gateway mission router — routes.toml session picker (Phase 2)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

_DEFAULT_ROUTES = Path.home() / ".agent-lab" / "routes.toml"

_DEFAULT_ROUTE: dict[str, Any] = {
    "session_id": "assistant-home",
    "gate_profile": "assistant",
}


def routes_config_path() -> Path:
    raw = (os.getenv("AGENT_LAB_ROUTES_CONFIG") or "").strip()
    return Path(raw).expanduser() if raw else _DEFAULT_ROUTES


def load_routes_config() -> dict[str, Any]:
    path = routes_config_path()
    if not path.is_file():
        return {"route": [], "default": dict(_DEFAULT_ROUTE)}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"route": [], "default": dict(_DEFAULT_ROUTE)}
    if not isinstance(raw, dict):
        return {"route": [], "default": dict(_DEFAULT_ROUTE)}
    routes = raw.get("route")
    if routes is None:
        routes = []
    if isinstance(routes, dict):
        routes = [routes]
    default = raw.get("default")
    if not isinstance(default, dict):
        default = dict(_DEFAULT_ROUTE)
    return {"route": routes, "default": default}


def _match_route(
    route: dict[str, Any],
    *,
    channel: str,
    text: str,
    hook_id: str | None,
    schedule_id: str | None,
) -> bool:
    match = route.get("match")
    if not isinstance(match, dict):
        return False
    if str(match.get("channel") or "") != channel:
        return False
    prefix = str(match.get("prefix") or "")
    if prefix and not text.startswith(prefix):
        return False
    expected_hook = match.get("hook_id")
    if expected_hook is not None and str(expected_hook) != str(hook_id or ""):
        return False
    expected_sched = match.get("schedule_id")
    if expected_sched is not None and str(expected_sched) != str(schedule_id or ""):
        return False
    return True


def route_inbound(
    *,
    channel: str,
    text: str = "",
    hook_id: str | None = None,
    schedule_id: str | None = None,
    chat_id: int | str | None = None,
) -> dict[str, Any]:
    """First-match wins; returns session_id + gate_profile + stripped text."""
    cfg = load_routes_config()
    chosen: dict[str, Any] | None = None
    prefix = ""
    for route in cfg.get("route") or []:
        if not isinstance(route, dict):
            continue
        if _match_route(
            route,
            channel=channel,
            text=text,
            hook_id=hook_id,
            schedule_id=schedule_id,
        ):
            chosen = route
            match = route.get("match") or {}
            prefix = str(match.get("prefix") or "")
            break
    if chosen is None:
        chosen = dict(cfg.get("default") or _DEFAULT_ROUTE)

    body = text[len(prefix) :].strip() if prefix else text.strip()
    session_id = str(chosen.get("session_id") or _DEFAULT_ROUTE["session_id"])
    gate_profile = str(chosen.get("gate_profile") or chosen.get("lane") or "assistant")
    if gate_profile not in ("dev", "assistant"):
        gate_profile = "assistant"
    return {
        "session_id": session_id,
        "gate_profile": gate_profile,
        "template_id": chosen.get("template_id"),
        "workspace": chosen.get("workspace"),
        "sandbox": chosen.get("sandbox"),
        "prefix": prefix,
        "text": body,
        "channel": channel,
        "chat_id": chat_id,
        "hook_id": hook_id,
        "schedule_id": schedule_id,
    }


def public_routes_payload() -> dict[str, Any]:
    cfg = load_routes_config()
    return {
        "path": str(routes_config_path()),
        "routes": cfg.get("route") or [],
        "default": cfg.get("default") or _DEFAULT_ROUTE,
    }
