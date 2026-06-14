"""Discord adapter — webhook ingress + optional outbound webhook URL."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from agent_lab.gateway.router import route_inbound


def _discord_cfg(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("discord") or {})


class DiscordGatewayAdapter:
    adapter_id = "discord"
    channel = "discord"

    def public_info(self) -> dict[str, Any]:
        cfg = _discord_cfg({})
        from agent_lab.gateway.config import load_gateway_config

        cfg = _discord_cfg(load_gateway_config())
        return {
            "channel": self.channel,
            "ingress": True,
            "egress": bool(str(cfg.get("webhook_url") or "").strip()),
            "webhook_url_set": bool(str(cfg.get("webhook_url") or "").strip()),
            "allowed_channel_ids": list(cfg.get("allowed_channel_ids") or []),
        }

    def is_enabled(self, config: dict[str, Any]) -> bool:
        cfg = _discord_cfg(config)
        return bool(str(cfg.get("webhook_url") or "").strip()) or bool(cfg.get("allow_ingress_without_webhook"))

    def _allowed_channel(self, config: dict[str, Any], channel_id: str | None) -> bool:
        cfg = _discord_cfg(config)
        allowed = [str(x) for x in (cfg.get("allowed_channel_ids") or []) if str(x).strip()]
        if not allowed:
            return True
        return channel_id is not None and str(channel_id) in allowed

    def process_ingress(self, payload: dict[str, Any]) -> dict[str, Any]:
        from agent_lab.gateway.config import load_gateway_config

        cfg = load_gateway_config()
        if not self.is_enabled(cfg) and not _discord_cfg(cfg).get("allow_ingress_without_webhook"):
            return {"ok": False, "reason": "discord_not_configured"}

        # Discord interaction or simplified `{ "content": "..." }` payload.
        content = str(payload.get("content") or "").strip()
        channel_id = payload.get("channel_id")
        if not content:
            interaction = payload.get("interaction")
            if isinstance(interaction, dict):
                data = interaction.get("data") or {}
                content = str(data.get("name") or data.get("custom_id") or "").strip()
                if content and not content.startswith("/"):
                    content = f"/{content}"
        if not content:
            return {"ok": False, "reason": "content_required"}

        if not self._allowed_channel(cfg, str(channel_id) if channel_id is not None else None):
            return {"ok": False, "reason": "channel_not_allowed", "channel_id": channel_id}

        prefix = str(_discord_cfg(cfg).get("prefix") or "")
        text = content if content.startswith("/") else f"{prefix}{content}".strip()
        routed = route_inbound(channel="discord", text=text)
        from agent_lab.gateway.telegram_adapter import handle_gateway_command

        result = handle_gateway_command(
            session_id=str(routed.get("session_id") or ""),
            text=str(routed.get("text") or text),
            gate_profile=str(routed.get("gate_profile") or "assistant"),
        )
        reply = str(result.get("reply") or "")
        if reply and str(_discord_cfg(cfg).get("webhook_url") or "").strip():
            self._post_webhook(cfg, reply)
        return {"ok": True, "route": routed, **result}

    def _post_webhook(self, config: dict[str, Any], content: str) -> dict[str, Any]:
        url = str(_discord_cfg(config).get("webhook_url") or "").strip()
        if not url:
            return {"ok": True, "skipped": True, "reason": "no_webhook_url"}
        body = json.dumps({"content": content[:1900]}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "agent-lab-gateway/1"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return {"ok": 200 <= resp.status < 300, "status": resp.status}
        except urllib.error.HTTPError as exc:
            return {"ok": False, "status": exc.code, "error": str(exc)}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {"ok": False, "error": str(exc)}

    def notify(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        from agent_lab.gateway.config import load_gateway_config

        cfg = load_gateway_config()
        url = str(_discord_cfg(cfg).get("webhook_url") or "").strip()
        if not url:
            return {"ok": True, "skipped": True, "reason": "no_webhook_url"}
        session_id = str(payload.get("session_id") or "")
        if event == "inbox_pending":
            item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
            prompt = str(item.get("prompt") or item.get("summary") or item.get("id") or "Inbox")
            kind = str(item.get("kind") or "item")
            item_id = str(item.get("id") or "")
            text = f"**[{session_id}]** inbox `{kind}`\n{prompt[:500]}\nResolve: `/resolve {item_id} <answer>`"
        elif event == "merge_ready":
            exec_id = str(payload.get("execution_id") or "")
            profile = str(payload.get("gate_profile") or "")
            text = (
                f"**[{session_id}]** merge ready\n`{exec_id}` (profile: {profile})\n`/approve merge` or `/approve auto`"
            )
        elif event == "gate_blocked":
            reason = str(payload.get("block_reason") or payload.get("block_source") or "blocked")
            text = f"**[{session_id}]** gate blocked\n{reason[:500]}"
        elif event == "schedule_tick":
            schedule_id = str(payload.get("schedule_id") or "")
            text = f"**[{session_id}]** schedule `{schedule_id}` tick"
        elif event == "auto_merge_blocked":
            exec_id = str(payload.get("execution_id") or "")
            reason = str(payload.get("reason") or "auto_merge_not_eligible")
            text = f"**[{session_id}]** auto-merge blocked\n`{exec_id}` — {reason[:240]}\n`/approve merge`"
        else:
            return {"ok": True, "skipped": True, "reason": "event_not_handled"}
        return self._post_webhook(cfg, text)
