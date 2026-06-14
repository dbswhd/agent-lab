"""Slack adapter — Events API ingress + Incoming Webhook egress."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any

from agent_lab.gateway.router import route_inbound


def _slack_cfg(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("slack") or {})


def verify_slack_signature(
    signing_secret: str,
    *,
    timestamp: str,
    body: bytes,
    signature: str,
) -> bool:
    secret = signing_secret.strip()
    if not secret or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > 60 * 5:
        return False
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    digest = hmac.new(secret.encode("utf-8"), basestring.encode("utf-8"), hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, signature)


class SlackGatewayAdapter:
    adapter_id = "slack"
    channel = "slack"

    def public_info(self) -> dict[str, Any]:
        from agent_lab.gateway.config import load_gateway_config

        cfg = _slack_cfg(load_gateway_config())
        return {
            "channel": self.channel,
            "ingress": True,
            "egress": bool(str(cfg.get("webhook_url") or "").strip()),
            "webhook_url_set": bool(str(cfg.get("webhook_url") or "").strip()),
            "signing_secret_set": bool(str(cfg.get("signing_secret") or "").strip()),
            "allowed_channel_ids": list(cfg.get("allowed_channel_ids") or []),
        }

    def is_enabled(self, config: dict[str, Any]) -> bool:
        cfg = _slack_cfg(config)
        if not cfg.get("enabled"):
            return False
        if bool(str(cfg.get("webhook_url") or "").strip()):
            return True
        if bool(str(cfg.get("bot_token") or "").strip()):
            return True
        return bool(cfg.get("allow_ingress_without_webhook"))

    def _allowed_channel(self, config: dict[str, Any], channel_id: str | None) -> bool:
        cfg = _slack_cfg(config)
        allowed = [str(x) for x in (cfg.get("allowed_channel_ids") or []) if str(x).strip()]
        if not allowed:
            return True
        return channel_id is not None and str(channel_id) in allowed

    def _verify_request(self, cfg: dict[str, Any], payload: dict[str, Any]) -> bool:
        secret = str(_slack_cfg(cfg).get("signing_secret") or "").strip()
        if not secret:
            return True
        headers = payload.get("_headers")
        raw_body = payload.get("_raw_body")
        if not isinstance(headers, dict) or not isinstance(raw_body, (bytes, bytearray)):
            return False
        sig = str(headers.get("X-Slack-Signature") or headers.get("x-slack-signature") or "")
        ts = str(headers.get("X-Slack-Request-Timestamp") or headers.get("x-slack-request-timestamp") or "")
        return verify_slack_signature(secret, timestamp=ts, body=bytes(raw_body), signature=sig)

    def process_ingress(self, payload: dict[str, Any]) -> dict[str, Any]:
        from agent_lab.gateway.config import load_gateway_config

        cfg = load_gateway_config()
        if not self.is_enabled(cfg):
            return {"ok": False, "reason": "slack_not_configured"}

        if not self._verify_request(cfg, payload):
            return {"ok": False, "reason": "invalid_signature"}

        if payload.get("type") == "url_verification":
            return {"ok": True, "challenge": payload.get("challenge")}

        content = str(payload.get("content") or "").strip()
        channel_id = payload.get("channel_id")
        event = payload.get("event")

        if payload.get("type") == "event_callback" and isinstance(event, dict):
            if event.get("bot_id") or event.get("subtype"):
                return {"ok": True, "skipped": True, "reason": "bot_or_subtype_message"}
            content = str(event.get("text") or "").strip()
            channel_id = channel_id or event.get("channel")

        if not content and isinstance(event, dict):
            content = str(event.get("text") or "").strip()
            channel_id = channel_id or event.get("channel")
        if not content:
            return {"ok": False, "reason": "content_required"}

        if not self._allowed_channel(cfg, str(channel_id) if channel_id else None):
            return {"ok": False, "reason": "channel_not_allowed", "channel_id": channel_id}

        prefix = str(_slack_cfg(cfg).get("prefix") or "")
        text = content if content.startswith("/") else f"{prefix}{content}".strip()
        routed = route_inbound(channel="slack", text=text)
        from agent_lab.gateway.telegram_adapter import handle_gateway_command

        result = handle_gateway_command(
            session_id=str(routed.get("session_id") or ""),
            text=str(routed.get("text") or text),
            gate_profile=str(routed.get("gate_profile") or "assistant"),
        )
        reply = str(result.get("reply") or "")
        if reply:
            self._post_webhook(cfg, reply)
        return {"ok": True, "route": routed, **result}

    def _post_webhook(self, config: dict[str, Any], content: str) -> dict[str, Any]:
        url = str(_slack_cfg(config).get("webhook_url") or "").strip()
        if not url:
            return {"ok": True, "skipped": True, "reason": "no_webhook_url"}
        body = json.dumps({"text": content[:3000]}, ensure_ascii=False).encode("utf-8")
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
        session_id = str(payload.get("session_id") or "")
        if event == "inbox_pending":
            item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
            prompt = str(item.get("prompt") or item.get("summary") or item.get("id") or "Inbox")
            kind = str(item.get("kind") or "item")
            text = f"*[{session_id}]* inbox `{kind}`\n{prompt[:500]}"
        elif event == "merge_ready":
            exec_id = str(payload.get("execution_id") or "")
            text = f"*[{session_id}]* merge ready\n`{exec_id}` — /approve merge"
        elif event == "gate_blocked":
            reason = str(payload.get("block_reason") or payload.get("block_source") or "blocked")
            text = f"*[{session_id}]* gate blocked\n{reason[:500]}"
        elif event == "schedule_tick":
            schedule_id = str(payload.get("schedule_id") or "")
            text = f"*[{session_id}]* schedule `{schedule_id}` tick"
        elif event == "auto_merge_blocked":
            exec_id = str(payload.get("execution_id") or "")
            reason = str(payload.get("reason") or "auto_merge_not_eligible")
            text = (
                f"*[{session_id}]* auto-merge blocked\n"
                f"`{exec_id}` — {reason[:240]}\n"
                f"/approve merge"
            )
        else:
            return {"ok": True, "skipped": True, "reason": "event_not_handled"}
        return self._post_webhook(cfg, text)
