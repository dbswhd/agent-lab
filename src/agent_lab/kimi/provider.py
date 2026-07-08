"""KIMI (Moonshot) live adapter — OpenAI-compatible, usage-exposing api provider.

Becomes a live substitute in the dynamic roster: invocation rotates through the
provider's N-account secret chain (account_chain.call_with_account_chain) so an
exhausted KIMI key fails over to the next in-turn, per the auth_kind seam.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from agent_lab.env_flags import env_bool

DEFAULT_ENDPOINT = "https://api.moonshot.ai/v1"
DEFAULT_MODEL = "kimi-k2"


def kimi_endpoint() -> str:
    return (os.getenv("AGENT_LAB_KIMI_ENDPOINT") or "").strip() or DEFAULT_ENDPOINT


def kimi_model() -> str:
    return (os.getenv("AGENT_LAB_KIMI_MODEL") or "").strip() or DEFAULT_MODEL


def model_label() -> str:
    return f"kimi:{kimi_model()}"


def _mock_enabled() -> bool:
    return env_bool("AGENT_LAB_MOCK_AGENTS")


def is_available() -> bool:
    """KIMI is available when it has at least one usable account in its chain."""
    if _mock_enabled():
        return True
    from agent_lab.credential_store import get_account_chain

    return bool(get_account_chain("kimi"))


def respond(
    system: str,
    user: str,
    *,
    on_activity: Callable[[str], None] | None = None,
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None = None,
    **_kwargs: Any,
) -> str:
    """First-class room substitute: emits activity + streams like cloud agents.

    Accepts the full call_agent_reply kwarg surface (session_folder/permissions/
    request_structured_envelope/inbox_mcp are absorbed — KIMI is a plain chat
    provider with no tool/MCP loop). The envelope, when requested, is carried by
    the system prompt and parsed downstream by merge_structured_reply.
    """
    if on_activity:
        on_activity(f"[net] {model_label()} /chat/completions")
    if _mock_enabled():
        snippet = " ".join((user or "").strip().split())[:100]
        text = f"[mock:KIMI] ACK — {snippet or '(empty)'}"
    else:
        from agent_lab.account_chain import call_with_account_chain
        from agent_lab.openai_compat import chat_completion

        def _call(api_key: str | None) -> str:
            if not api_key:
                raise RuntimeError("KIMI API key not set (api key not set)")
            return chat_completion(
                endpoint=kimi_endpoint(), model=kimi_model(), system=system, user=user, api_key=api_key
            )

        text = call_with_account_chain("kimi", _call)
    _stream(on_bridge_event, text)
    return text


def _stream(on_bridge_event: Callable[[str, dict[str, Any]], None] | None, text: str) -> None:
    if not on_bridge_event or not text:
        return
    from agent_lab.room.sse_stream import chunk_text

    for chunk in chunk_text(text, chunk_size=24):
        on_bridge_event("text", {"text": chunk})
