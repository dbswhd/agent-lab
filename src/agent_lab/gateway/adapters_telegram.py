"""Telegram adapter — wraps Phase 2 telegram_adapter."""

from __future__ import annotations

from typing import Any

from agent_lab.gateway.config import load_gateway_config


class TelegramGatewayAdapter:
    adapter_id = "telegram"
    channel = "telegram"

    def public_info(self) -> dict[str, Any]:
        cfg = load_gateway_config()
        tg = dict(cfg.get("telegram") or {})
        token = str(tg.get("bot_token") or "")
        return {
            "channel": self.channel,
            "ingress": True,
            "egress": True,
            "telegram": {
                "enabled": bool(tg.get("enabled")),
                "allowed_chat_ids": list(tg.get("allowed_chat_ids") or []),
                "bot_token_set": bool(token.strip()),
            },
        }

    def is_enabled(self, config: dict[str, Any]) -> bool:
        tg = dict(config.get("telegram") or {})
        return bool(tg.get("enabled"))

    def process_ingress(self, payload: dict[str, Any]) -> dict[str, Any]:
        from agent_lab.gateway.telegram_adapter import process_telegram_update

        update = payload.get("update")
        if not isinstance(update, dict):
            return {"ok": False, "reason": "update_required"}
        return process_telegram_update(update)

    def notify(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        from agent_lab.gateway import telegram_adapter as tg

        if event == "inbox_pending":
            session_id = str(payload.get("session_id") or "")
            item = payload.get("item")
            if not session_id or not isinstance(item, dict):
                return {"ok": True, "skipped": True, "reason": "missing_item"}
            return tg.notify_inbox_pending(session_id, item)
        if event == "merge_ready":
            return tg.notify_merge_ready(payload)
        if event == "gate_blocked":
            return tg.notify_gate_blocked(payload)
        if event == "schedule_tick":
            return tg.notify_schedule_tick(payload)
        if event == "auto_merge_blocked":
            return tg.notify_auto_merge_blocked(payload)
        return {"ok": True, "skipped": True, "reason": "event_not_handled"}


def telegram_adapter_enabled() -> bool:
    cfg = load_gateway_config()
    return TelegramGatewayAdapter().is_enabled(cfg)
