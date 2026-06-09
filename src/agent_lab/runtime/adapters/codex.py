"""Codex openai-oauth proxy transport — dev-only opt-in (MB-11)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

from agent_lab.agent_models import DEFAULT_CODEX_MODEL


def codex_proxy_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_CODEX_PROXY") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def codex_proxy_base_url() -> str:
    raw = (os.getenv("AGENT_LAB_CODEX_PROXY_URL") or "").strip()
    if raw:
        return raw.rstrip("/")
    return "http://127.0.0.1:10531/v1"


def codex_proxy_model(*, room_turn: bool) -> str:
    if room_turn:
        return (
            os.getenv("CODEX_PROXY_ROOM_MODEL")
            or os.getenv("CODEX_MODEL")
            or DEFAULT_CODEX_MODEL
        )
    return os.getenv("CODEX_PROXY_MODEL") or os.getenv("CODEX_MODEL") or DEFAULT_CODEX_MODEL


def can_route_codex_proxy(
    *,
    inbox_mcp: bool = False,
    execute_plugins: bool = False,
) -> bool:
    """Proxy is text-only — no MCP/plugins/shell tools."""
    if not codex_proxy_enabled():
        return False
    if inbox_mcp or execute_plugins:
        return False
    return True


def probe_codex_proxy(*, timeout_sec: float = 3.0) -> dict[str, Any]:
    if not codex_proxy_enabled():
        return {
            "enabled": False,
            "ok": False,
            "detail": "AGENT_LAB_CODEX_PROXY not set",
            "base_url": codex_proxy_base_url(),
        }
    url = f"{codex_proxy_base_url()}/models"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return {
            "enabled": True,
            "ok": False,
            "detail": detail or f"HTTP {exc.code}",
            "base_url": codex_proxy_base_url(),
        }
    except OSError as exc:
        return {
            "enabled": True,
            "ok": False,
            "detail": str(exc)[:200],
            "base_url": codex_proxy_base_url(),
            "next": "Run: npx openai-oauth (local proxy on :10531)",
        }
    models: list[str] = []
    try:
        payload = json.loads(body)
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            models = [str(row.get("id") or "") for row in data if isinstance(row, dict)]
    except json.JSONDecodeError:
        pass
    return {
        "enabled": True,
        "ok": True,
        "detail": f"{len(models)} model(s)" if models else "proxy reachable",
        "base_url": codex_proxy_base_url(),
        "models": [m for m in models if m][:8],
    }


def invoke_codex_proxy(
    system: str,
    user: str,
    *,
    room_turn: bool = False,
    on_activity: Callable[[str], None] | None = None,
) -> str:
    if on_activity:
        on_activity("Codex proxy 요청")
    model = codex_proxy_model(room_turn=room_turn)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system.strip()},
            {"role": "user", "content": user.strip()},
        ],
    }
    url = f"{codex_proxy_base_url()}/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(
            f"Codex proxy HTTP {exc.code}: {detail or exc.reason}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Codex proxy unreachable at {codex_proxy_base_url()}: {exc}"
        ) from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Codex proxy returned non-JSON response") from exc
    choices = parsed.get("choices") if isinstance(parsed, dict) else None
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Codex proxy returned empty choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise RuntimeError("Codex proxy missing message")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        if on_activity:
            on_activity("Codex proxy 응답")
        return content.strip()
    raise RuntimeError("Codex proxy returned empty content")
