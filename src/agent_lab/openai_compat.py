"""Minimal OpenAI-compatible chat-completion helper.

Shared by the local (Ollama) and KIMI (Moonshot) adapters so the dynamic room's
api/local providers reach their endpoints through one grounded code path.
"""

from __future__ import annotations

import json
import urllib.request


def chat_completion(
    *,
    endpoint: str,
    model: str,
    system: str,
    user: str,
    api_key: str | None = None,
    timeout: float = 120.0,
) -> str:
    """POST an OpenAI-compatible /chat/completions request and return the message text."""
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system or ""},
                {"role": "user", "content": user or ""},
            ],
            "stream": False,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        f"{endpoint.rstrip('/')}/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - user-configured endpoint
        data = json.loads(resp.read().decode("utf-8"))
    choices = data.get("choices") if isinstance(data, dict) else None
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            return str(message.get("content") or "")
    return ""
