"""Gateway configuration — ~/.agent-lab/gateway.toml."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path.home() / ".agent-lab" / "gateway.toml"

_DEFAULT_CONFIG: dict[str, Any] = {
    "outbound": {
        "enabled": False,
        "urls": [],
        "secret": "",
        "events": [
            "inbox_pending",
            "merge_ready",
            "schedule_tick",
            "gate_blocked",
            "auto_merge_blocked",
        ],
        "timeout_s": 5,
    },
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "allowed_chat_ids": [],
    },
    "discord": {
        "webhook_url": "",
        "allowed_channel_ids": [],
        "allow_ingress_without_webhook": True,
    },
    "slack": {
        "enabled": False,
        "webhook_url": "",
        "bot_token": "",
        "signing_secret": "",
        "allowed_channel_ids": [],
        "prefix": "",
    },
    "hybrid": {
        "enabled": False,
        "relay_url": "",
        "relay_secret": "",
        "relay_when": "daemon_offline",
        "timeout_s": 8,
    },
    "adapters": {
        "enabled": ["telegram", "webhook_inbound", "cli", "discord", "slack"],
    },
}


def gateway_config_path() -> Path:
    raw = (os.getenv("AGENT_LAB_GATEWAY_CONFIG") or "").strip()
    return Path(raw).expanduser() if raw else _DEFAULT_PATH


def _normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    out = {k: v if not isinstance(v, dict) else dict(v) for k, v in _DEFAULT_CONFIG.items()}
    outbound = data.get("outbound")
    if isinstance(outbound, dict):
        merged = {**out["outbound"], **outbound}
        urls = merged.get("urls")
        if isinstance(urls, str):
            merged["urls"] = [u.strip() for u in urls.split(",") if u.strip()]
        elif isinstance(urls, list):
            merged["urls"] = [str(u).strip() for u in urls if str(u).strip()]
        events = merged.get("events")
        if isinstance(events, str):
            merged["events"] = [e.strip() for e in events.split(",") if e.strip()]
        out["outbound"] = merged
    telegram = data.get("telegram")
    if isinstance(telegram, dict):
        merged = {**out["telegram"], **telegram}
        chat_ids = merged.get("allowed_chat_ids")
        if isinstance(chat_ids, (int, str)) and str(chat_ids).strip():
            merged["allowed_chat_ids"] = [int(chat_ids)]
        elif isinstance(chat_ids, list):
            merged["allowed_chat_ids"] = [
                int(c) for c in chat_ids if str(c).strip()
            ]
        out["telegram"] = merged
    discord = data.get("discord")
    if isinstance(discord, dict):
        out["discord"] = {**out["discord"], **discord}
    slack = data.get("slack")
    if isinstance(slack, dict):
        out["slack"] = {**out["slack"], **slack}
    hybrid = data.get("hybrid")
    if isinstance(hybrid, dict):
        out["hybrid"] = {**out["hybrid"], **hybrid}
    adapters = data.get("adapters")
    if isinstance(adapters, dict):
        out["adapters"] = {**out["adapters"], **adapters}
    elif isinstance(adapters, list):
        out["adapters"] = {"enabled": [str(x) for x in adapters]}
    return out


def load_gateway_config() -> dict[str, Any]:
    path = gateway_config_path()
    if not path.is_file():
        return _normalize_config({})
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return _normalize_config({})
    if not isinstance(raw, dict):
        return _normalize_config({})
    return _normalize_config(raw)


def public_gateway_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config if config is not None else load_gateway_config()
    outbound = dict(cfg.get("outbound") or {})
    telegram = dict(cfg.get("telegram") or {})
    discord = dict(cfg.get("discord") or {})
    slack = dict(cfg.get("slack") or {})
    secret = str(outbound.get("secret") or "")
    token = str(telegram.get("bot_token") or "")
    from agent_lab.gateway.hybrid_relay import public_hybrid_payload

    return {
        "path": str(gateway_config_path()),
        "outbound": {
            "enabled": bool(outbound.get("enabled")),
            "urls": list(outbound.get("urls") or []),
            "events": list(outbound.get("events") or []),
            "timeout_s": int(outbound.get("timeout_s") or 5),
            "secret_set": bool(secret.strip()),
        },
        "telegram": {
            "enabled": bool(telegram.get("enabled")),
            "allowed_chat_ids": list(telegram.get("allowed_chat_ids") or []),
            "bot_token_set": bool(token.strip()),
        },
        "discord": {
            "webhook_url_set": bool(str(discord.get("webhook_url") or "").strip()),
            "allowed_channel_ids": list(discord.get("allowed_channel_ids") or []),
        },
        "slack": {
            "enabled": bool(slack.get("enabled")),
            "webhook_url_set": bool(str(slack.get("webhook_url") or "").strip()),
            "bot_token_set": bool(str(slack.get("bot_token") or "").strip()),
            "allowed_channel_ids": list(slack.get("allowed_channel_ids") or []),
        },
        "hybrid": public_hybrid_payload(cfg),
    }


def _toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def save_gateway_config(patch: dict[str, Any]) -> dict[str, Any]:
    current = load_gateway_config()
    if "outbound" in patch and isinstance(patch["outbound"], dict):
        ob = dict(current.get("outbound") or {})
        for key, value in patch["outbound"].items():
            if value is not None:
                ob[key] = value
        current["outbound"] = ob
    if "telegram" in patch and isinstance(patch["telegram"], dict):
        tg = dict(current.get("telegram") or {})
        for key, value in patch["telegram"].items():
            if value is not None:
                tg[key] = value
        current["telegram"] = tg
    if "discord" in patch and isinstance(patch["discord"], dict):
        dc = dict(current.get("discord") or {})
        for key, value in patch["discord"].items():
            if value is not None:
                dc[key] = value
        current["discord"] = dc
    if "slack" in patch and isinstance(patch["slack"], dict):
        sl = dict(current.get("slack") or {})
        for key, value in patch["slack"].items():
            if value is not None:
                sl[key] = value
        current["slack"] = sl
    if "hybrid" in patch and isinstance(patch["hybrid"], dict):
        hy = dict(current.get("hybrid") or {})
        for key, value in patch["hybrid"].items():
            if value is not None:
                hy[key] = value
        current["hybrid"] = hy
    if "adapters" in patch and isinstance(patch["adapters"], dict):
        ad = dict(current.get("adapters") or {})
        for key, value in patch["adapters"].items():
            if value is not None:
                ad[key] = value
        current["adapters"] = ad
    current = _normalize_config(current)

    path = gateway_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    outbound = current["outbound"]
    telegram = current["telegram"]
    discord = current["discord"]
    slack = current.get("slack") or {}
    hybrid = current["hybrid"]
    adapters = current["adapters"]
    lines = [
        "# Agent Lab gateway — docs/MISSION-OS-DIRECTION.md",
        "",
        "[outbound]",
        f"enabled = {'true' if outbound.get('enabled') else 'false'}",
        f"timeout_s = {int(outbound.get('timeout_s') or 5)}",
    ]
    secret = str(outbound.get("secret") or "")
    if secret.strip():
        lines.append(f"secret = {_toml_quote(secret)}")
    urls = outbound.get("urls") or []
    if urls:
        lines.append("urls = [")
        for url in urls:
            lines.append(f"  {_toml_quote(str(url))},")
        lines.append("]")
    events = outbound.get("events") or []
    if events:
        lines.append("events = [")
        for event in events:
            lines.append(f"  {_toml_quote(str(event))},")
        lines.append("]")
    lines.extend(
        [
            "",
            "[telegram]",
            f"enabled = {'true' if telegram.get('enabled') else 'false'}",
        ]
    )
    token = str(telegram.get("bot_token") or "")
    if token.strip():
        lines.append(f"bot_token = {_toml_quote(token)}")
    chat_ids = telegram.get("allowed_chat_ids") or []
    if chat_ids:
        lines.append("allowed_chat_ids = [")
        for chat_id in chat_ids:
            lines.append(f"  {int(chat_id)},")
        lines.append("]")
    lines.extend(
        [
            "",
            "[discord]",
        ]
    )
    discord_url = str(discord.get("webhook_url") or "")
    if discord_url.strip():
        lines.append(f"webhook_url = {_toml_quote(discord_url)}")
    dc_channels = discord.get("allowed_channel_ids") or []
    if dc_channels:
        lines.append("allowed_channel_ids = [")
        for channel_id in dc_channels:
            lines.append(f"  {_toml_quote(str(channel_id))},")
        lines.append("]")
    lines.extend(["", "[slack]", f"enabled = {'true' if slack.get('enabled') else 'false'}"])
    slack_url = str(slack.get("webhook_url") or "")
    if slack_url.strip():
        lines.append(f"webhook_url = {_toml_quote(slack_url)}")
    slack_token = str(slack.get("bot_token") or "")
    if slack_token.strip():
        lines.append(f"bot_token = {_toml_quote(slack_token)}")
    slack_channels = slack.get("allowed_channel_ids") or []
    if slack_channels:
        lines.append("allowed_channel_ids = [")
        for channel_id in slack_channels:
            lines.append(f"  {_toml_quote(str(channel_id))},")
        lines.append("]")
    lines.extend(
        [
            "",
            "[hybrid]",
            f"enabled = {'true' if hybrid.get('enabled') else 'false'}",
            f"relay_when = {_toml_quote(str(hybrid.get('relay_when') or 'daemon_offline'))}",
            f"timeout_s = {int(hybrid.get('timeout_s') or 8)}",
        ]
    )
    relay_url = str(hybrid.get("relay_url") or "")
    if relay_url.strip():
        lines.append(f"relay_url = {_toml_quote(relay_url)}")
    relay_secret = str(hybrid.get("relay_secret") or "")
    if relay_secret.strip():
        lines.append(f"relay_secret = {_toml_quote(relay_secret)}")
    enabled = list(adapters.get("enabled") or [])
    if enabled:
        lines.extend(["", "[adapters]", "enabled = ["])
        for adapter_id in enabled:
            lines.append(f"  {_toml_quote(str(adapter_id))},")
        lines.append("]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return current
