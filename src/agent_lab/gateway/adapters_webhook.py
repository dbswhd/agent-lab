"""Webhook inbound adapter — routes.toml session picker."""

from __future__ import annotations

from typing import Any

from agent_lab.gateway.router import route_inbound


class WebhookInboundAdapter:
    adapter_id = "webhook_inbound"
    channel = "webhook"

    def public_info(self) -> dict[str, Any]:
        from agent_lab.gateway.router import public_routes_payload

        routes = public_routes_payload()
        return {
            "channel": self.channel,
            "ingress": True,
            "egress": False,
            "routes_path": routes.get("path"),
            "route_count": len(routes.get("routes") or []),
        }

    def is_enabled(self, config: dict[str, Any]) -> bool:
        return True

    def process_ingress(self, payload: dict[str, Any]) -> dict[str, Any]:
        hook_id = str(payload.get("hook_id") or "")
        text = str(payload.get("text") or "")
        body = payload.get("payload")
        routed = route_inbound(channel="webhook", text=text, hook_id=hook_id or None)
        result: dict[str, Any] = {
            "ok": True,
            "hook_id": hook_id,
            "route": routed,
            "payload": body,
        }
        cmd = str(routed.get("text") or text).strip()
        if cmd:
            from agent_lab.gateway.telegram_adapter import handle_gateway_command

            cmd_result = handle_gateway_command(
                session_id=str(routed.get("session_id") or ""),
                text=cmd,
                gate_profile=str(routed.get("gate_profile") or "assistant"),
            )
            result["command"] = cmd_result
        return result

    def notify(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "skipped": True, "reason": "ingress_only"}
