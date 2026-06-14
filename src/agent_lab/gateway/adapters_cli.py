"""CLI gateway adapter — text commands for automation."""

from __future__ import annotations

from typing import Any

from agent_lab.gateway.router import route_inbound


class CliGatewayAdapter:
    adapter_id = "cli"
    channel = "cli"

    def public_info(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "ingress": True,
            "egress": False,
        }

    def is_enabled(self, config: dict[str, Any]) -> bool:
        return True

    def process_ingress(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        gate_profile = str(payload.get("gate_profile") or "assistant")
        if session_id:
            routed = {
                "session_id": session_id,
                "gate_profile": gate_profile,
                "text": text,
                "channel": self.channel,
            }
        else:
            routed = route_inbound(channel="cli", text=text)
            session_id = str(routed.get("session_id") or "")
            gate_profile = str(routed.get("gate_profile") or gate_profile)
        if not text:
            return {"ok": False, "reason": "text_required", "route": routed}
        from agent_lab.gateway.telegram_adapter import handle_gateway_command

        result = handle_gateway_command(
            session_id=session_id,
            text=text,
            gate_profile=gate_profile,
        )
        return {"ok": True, "route": routed, **result}

    def notify(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "skipped": True, "reason": "ingress_only"}
