"""Local/offline fallback provider (Ollama / OpenAI-compatible).

The always-available, cooldown-exempt floor of the dynamic resilient room: even
when every cloud account is exhausted, the local provider keeps the roster at
>=1 agent. Endpoint/model are tunable defaults; under AGENT_LAB_MOCK_AGENTS the
adapter returns a deterministic canned reply so the resilience path is testable
without a running local model.
"""

from __future__ import annotations

import os
from typing import Any

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


def respond(system: str, user: str, **_kwargs: Any) -> str:
    """Produce a local reply. Mock-safe; real path calls the OpenAI-compatible endpoint."""
    if _mock_enabled():
        snippet = " ".join((user or "").strip().split())[:100]
        return f"[mock:Local] ACK — {snippet or '(empty)'}"
    # Real path: OpenAI-compatible chat completion against the local endpoint.
    from agent_lab.openai_compat import chat_completion

    return chat_completion(endpoint=local_endpoint(), model=local_model(), system=system, user=user)
