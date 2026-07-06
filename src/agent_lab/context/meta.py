"""Enrich ContextBundle metadata — re-export from core (F12)."""

from __future__ import annotations

from agent_lab.core.context_meta import (  # noqa: F401
    apply_invoke_follow_to_context_meta,
    enrich_bundle_meta,
    summarize_turn_context,
)

__all__ = [
    "apply_invoke_follow_to_context_meta",
    "enrich_bundle_meta",
    "summarize_turn_context",
]
