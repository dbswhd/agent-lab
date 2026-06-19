"""Slash-command surface for the dynamic resilient room (gajae-code style).

Six commands manage auth/accounts/models/usage/roster:
  /login /logout /accounts /model /usage /agents
Writes go through credential_store; secrets are always masked in output.
This module is the parser + dispatcher; the room router exposes it over HTTP.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from agent_lab import agent_roster, provider_registry, usage_monitor
from agent_lab.consensus_gate import allocate_roles
from agent_lab.credential_store import (
    get_provider_accounts,
    mask_secret,
    set_provider_accounts,
)

SLASH_COMMANDS: tuple[str, ...] = ("login", "logout", "accounts", "model", "usage", "agents")


def parse_command(text: str) -> tuple[str, list[str]] | None:
    """Parse "/cmd arg1 arg2" -> ("cmd", [args]); None when not a slash command."""
    s = (text or "").strip()
    if not s.startswith("/"):
        return None
    parts = s[1:].split()
    if not parts:
        return None
    return parts[0].lower(), parts[1:]


def is_slash_command(text: str) -> bool:
    parsed = parse_command(text)
    return parsed is not None and parsed[0] in SLASH_COMMANDS


def _err(command: str, message: str) -> dict[str, Any]:
    return {"ok": False, "command": command, "error": message}


def _require_provider(command: str, args: list[str]) -> str | dict[str, Any]:
    if not args:
        return _err(command, "provider required")
    provider = args[0]
    if not provider_registry.is_registered(provider):
        return _err(command, f"unknown provider: {provider}")
    return provider


def _masked_accounts(provider: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for acct in get_provider_accounts(provider):
        ref = str(acct.get("secret_or_profile_ref") or acct.get("secret") or "")
        out.append(
            {
                "label": str(acct.get("label") or ""),
                "masked": mask_secret(ref),
                "priority": acct.get("priority"),
                "cooldown_until": acct.get("cooldown_until"),
            }
        )
    return out


def _login(args: list[str]) -> dict[str, Any]:
    provider = _require_provider("login", args)
    if isinstance(provider, dict):
        return provider
    kind = provider_registry.auth_kind(provider)
    if kind in ("oauth", "cli"):
        return {
            "ok": True,
            "command": "login",
            "provider": provider,
            "auth_kind": kind,
            "note": f"Run the {provider} CLI OAuth login; profiles are referenced, not stored as secrets.",
        }
    secret = args[1] if len(args) > 1 else ""
    if not secret:
        return _err("login", f"{provider} is an API provider; supply a key: /login {provider} <key>")
    accounts = get_provider_accounts(provider)
    accounts.append(
        {
            "label": f"account{len(accounts) + 1}",
            "secret_or_profile_ref": secret,
            "priority": len(accounts) + 1,
            "cooldown_until": 0.0,
        }
    )
    set_provider_accounts(provider, accounts)
    return {
        "ok": True,
        "command": "login",
        "provider": provider,
        "auth_kind": kind,
        "accounts": _masked_accounts(provider),
    }


def _logout(args: list[str]) -> dict[str, Any]:
    provider = _require_provider("logout", args)
    if isinstance(provider, dict):
        return provider
    set_provider_accounts(provider, [])
    return {"ok": True, "command": "logout", "provider": provider, "cleared": True}


def _accounts(args: list[str]) -> dict[str, Any]:
    provider = _require_provider("accounts", args)
    if isinstance(provider, dict):
        return provider
    sub = args[1].lower() if len(args) > 1 else "list"
    if sub == "list":
        return {"ok": True, "command": "accounts", "provider": provider, "accounts": _masked_accounts(provider)}
    if sub == "add":
        if len(args) < 4:
            return _err("accounts", "usage: /accounts <provider> add <label> <secret>")
        label, secret = args[2], args[3]
        accounts = get_provider_accounts(provider)
        accounts.append(
            {"label": label, "secret_or_profile_ref": secret, "priority": len(accounts) + 1, "cooldown_until": 0.0}
        )
        set_provider_accounts(provider, accounts)
        return {
            "ok": True,
            "command": "accounts",
            "provider": provider,
            "added": label,
            "accounts": _masked_accounts(provider),
        }
    if sub == "remove":
        if len(args) < 3:
            return _err("accounts", "usage: /accounts <provider> remove <label>")
        label = args[2]
        accounts = [a for a in get_provider_accounts(provider) if str(a.get("label") or "") != label]
        set_provider_accounts(provider, accounts)
        return {
            "ok": True,
            "command": "accounts",
            "provider": provider,
            "removed": label,
            "accounts": _masked_accounts(provider),
        }
    return _err("accounts", f"unknown subcommand: {sub}")


def _model(args: list[str]) -> dict[str, Any]:
    if args:
        composition = [tok for tok in ",".join(args).split(",") if tok.strip()]
        os.environ["AGENT_LAB_ROOM_MODELS"] = ",".join(composition)
        updated_flag = True
    else:
        composition = agent_roster.override_composition() or list(provider_registry.DEFAULT_ROSTER)
        updated_flag = False
    substitution = agent_roster.override_substitution() or list(provider_registry.DEFAULT_SUBSTITUTION_PRIORITY)
    return {
        "ok": True,
        "command": "model",
        "composition": composition,
        "substitution": substitution,
        "updated": updated_flag,
    }


def _usage(args: list[str]) -> dict[str, Any]:
    providers = [args[0]] if args and provider_registry.is_registered(args[0]) else provider_registry.provider_ids()
    rows: list[dict[str, Any]] = []
    for pid in providers:
        for acct in get_provider_accounts(pid):
            label = str(acct.get("label") or "")
            rows.append(
                {
                    "provider": pid,
                    "label": label,
                    "cooldown_active": usage_monitor.cooldown_active(pid, label),
                    "usage_exposing": provider_registry.is_usage_exposing(pid),
                }
            )
    return {"ok": True, "command": "usage", "rows": rows}


def _agents(args: list[str]) -> dict[str, Any]:
    from agent_lab.agents.registry import available_agents

    roster = [str(a) for a in agent_roster.resolve_active_agents(None, available_agents)]
    return {"ok": True, "command": "agents", "roster": roster, "roles": allocate_roles(roster)}


_HANDLERS: dict[str, Callable[[list[str]], dict[str, Any]]] = {
    "login": _login,
    "logout": _logout,
    "accounts": _accounts,
    "model": _model,
    "usage": _usage,
    "agents": _agents,
}


def dispatch(text: str) -> dict[str, Any]:
    parsed = parse_command(text)
    if parsed is None:
        return {"ok": False, "error": "not a slash command"}
    cmd, args = parsed
    handler = _HANDLERS.get(cmd)
    if handler is None:
        return _err(cmd, "unknown command")
    return handler(args)
