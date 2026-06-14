"""Gateway adapter protocol + registry (Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GatewayAdapter(Protocol):
    """Many entrances, one brain — ingress/egress per channel."""

    adapter_id: str
    channel: str

    def public_info(self) -> dict[str, Any]:
        """Settings registry row — no secrets."""

    def is_enabled(self, config: dict[str, Any]) -> bool: ...

    def process_ingress(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def notify(self, event: str, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AdapterRegistration:
    adapter: GatewayAdapter
    description: str


_REGISTRY: dict[str, AdapterRegistration] = {}


def register_adapter(adapter: GatewayAdapter, *, description: str = "") -> None:
    _REGISTRY[adapter.adapter_id] = AdapterRegistration(
        adapter=adapter,
        description=description or adapter.adapter_id,
    )


def get_adapter(adapter_id: str) -> GatewayAdapter | None:
    row = _REGISTRY.get(adapter_id)
    return row.adapter if row else None


def list_adapter_ids() -> list[str]:
    return sorted(_REGISTRY.keys())


def _enabled_ids(config: dict[str, Any]) -> set[str]:
    adapters = config.get("adapters")
    if isinstance(adapters, dict):
        raw = adapters.get("enabled")
        if isinstance(raw, list):
            return {str(x).strip() for x in raw if str(x).strip()}
    if isinstance(adapters, list):
        return {str(x).strip() for x in adapters if str(x).strip()}
    # Default: all registered adapters enabled.
    return set(_REGISTRY.keys())


def public_adapters_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    from agent_lab.gateway.config import load_gateway_config

    cfg = config if config is not None else load_gateway_config()
    enabled = _enabled_ids(cfg)
    rows: list[dict[str, Any]] = []
    for adapter_id, reg in sorted(_REGISTRY.items()):
        info = reg.adapter.public_info()
        info["id"] = adapter_id
        info["description"] = reg.description
        info["enabled"] = adapter_id in enabled and reg.adapter.is_enabled(cfg)
        rows.append(info)
    return {"adapters": rows, "enabled": sorted(enabled)}


def process_gateway_ingress(
    channel: str,
    payload: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from agent_lab.gateway.config import load_gateway_config

    cfg = config if config is not None else load_gateway_config()
    enabled = _enabled_ids(cfg)
    for reg in _REGISTRY.values():
        adapter = reg.adapter
        if adapter.channel != channel:
            continue
        if adapter.adapter_id not in enabled:
            return {"ok": False, "reason": "adapter_disabled", "adapter": adapter.adapter_id}
        if not adapter.is_enabled(cfg):
            return {"ok": False, "reason": "adapter_not_configured", "adapter": adapter.adapter_id}
        return adapter.process_ingress(payload)
    return {"ok": False, "reason": "unknown_channel", "channel": channel}


def fan_out_gateway_notify(
    event: str,
    payload: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Egress: outbound webhooks + adapter notify + hybrid relay when daemon offline."""
    from agent_lab.gateway.config import load_gateway_config
    from agent_lab.gateway.hybrid_relay import maybe_deliver_hybrid_relay
    from agent_lab.gateway.outbound import deliver_outbound_event

    cfg = config if config is not None else load_gateway_config()
    enabled = _enabled_ids(cfg)
    outbound = deliver_outbound_event(event, payload, config=cfg)
    adapter_results: list[dict[str, Any]] = []
    for reg in _REGISTRY.values():
        adapter = reg.adapter
        if adapter.adapter_id not in enabled or not adapter.is_enabled(cfg):
            continue
        try:
            adapter_results.append({"adapter": adapter.adapter_id, **adapter.notify(event, payload)})
        except Exception as exc:
            adapter_results.append({"adapter": adapter.adapter_id, "ok": False, "error": str(exc)})
    hybrid = maybe_deliver_hybrid_relay(event, payload, config=cfg)
    return {
        "ok": True,
        "event": event,
        "outbound": outbound,
        "adapters": adapter_results,
        "hybrid_relay": hybrid,
    }


def _bootstrap_adapters() -> None:
    if _REGISTRY:
        return
    from agent_lab.gateway.adapters_cli import CliGatewayAdapter
    from agent_lab.gateway.adapters_discord import DiscordGatewayAdapter
    from agent_lab.gateway.adapters_slack import SlackGatewayAdapter
    from agent_lab.gateway.adapters_telegram import TelegramGatewayAdapter
    from agent_lab.gateway.adapters_webhook import WebhookInboundAdapter

    register_adapter(TelegramGatewayAdapter(), description="Telegram two-way MVP")
    register_adapter(WebhookInboundAdapter(), description="CI / external webhook ingress")
    register_adapter(CliGatewayAdapter(), description="CLI / automation text ingress")
    register_adapter(DiscordGatewayAdapter(), description="Discord webhook ingress + notify")
    register_adapter(SlackGatewayAdapter(), description="Slack webhook ingress + notify")


_bootstrap_adapters()
