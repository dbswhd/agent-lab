"""Local/offline fallback provider (Ollama / OpenAI-compatible).

The always-available, cooldown-exempt floor of the dynamic resilient room: even
when every cloud account is exhausted, the local provider keeps the roster at
>=1 agent. Endpoint/model are tunable defaults; under AGENT_LAB_MOCK_AGENTS the
adapter returns a deterministic canned reply so the resilience path is testable
without a running local model.
"""

from __future__ import annotations

import os
from typing import Any, Callable

DEFAULT_ENDPOINT = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2"


def local_endpoint() -> str:
    return (os.getenv("AGENT_LAB_LOCAL_ENDPOINT") or "").strip() or DEFAULT_ENDPOINT


def local_model() -> str:
    return (os.getenv("AGENT_LAB_LOCAL_MODEL") or "").strip() or DEFAULT_MODEL


def model_label() -> str:
    return f"local:{local_model()}"


def is_available() -> bool:
    """The local fallback is always available (the >=1-agent floor)."""
    return True


def _mock_enabled() -> bool:
    return os.getenv("AGENT_LAB_MOCK_AGENTS", "").strip().lower() in {"1", "true", "yes", "on"}


def respond(
    system: str,
    user: str,
    *,
    on_activity: Callable[[str], None] | None = None,
    on_bridge_event: Callable[[str, dict[str, Any]], None] | None = None,
    **_kwargs: Any,
) -> str:
    """Produce a local reply — first-class room substitute (activity + streaming).

    Mock-safe; the real path calls the OpenAI-compatible endpoint. Extra
    call_agent_reply kwargs are absorbed (local has no tool/MCP loop).
    """
    if on_activity:
        on_activity(f"[net] {model_label()} /chat/completions")
    if _mock_enabled():
        snippet = " ".join((user or "").strip().split())[:100]
        text = f"[mock:Local] ACK — {snippet or '(empty)'}"
    else:
        from agent_lab.openai_compat import chat_completion

        text = chat_completion(endpoint=local_endpoint(), model=local_model(), system=system, user=user)
    _stream(on_bridge_event, text)
    return text


def _stream(on_bridge_event: Callable[[str, dict[str, Any]], None] | None, text: str) -> None:
    if not on_bridge_event or not text:
        return
    from agent_lab.room_sse_stream import chunk_text

    for chunk in chunk_text(text, chunk_size=24):
        on_bridge_event("text", {"text": chunk})
