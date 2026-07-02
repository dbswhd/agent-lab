"""Session-template routing hints for topic_router (lightweight SSOT)."""

from __future__ import annotations

from typing import Any

# Keep in sync with routing_hints on entries in session/setup.py template defs.
_TEMPLATE_ROUTING_HINTS: dict[str, dict[str, Any]] = {
    "general": {},
    "book-layout": {},
    "book-content": {},
    "trading-mission": {"response_contract_bias": "evidence_first"},
    "trading-thin": {},
    "trading-offline": {},
}


def template_routing_hints(template_id: str | None) -> dict[str, Any]:
    """Optional session-template routing biases for topic_router."""
    tid = (template_id or "general").strip().lower()
    try:
        from agent_lab.session.setup import resolve_session_template

        tpl = resolve_session_template(template_id)
        hints = tpl.get("routing_hints")
        if isinstance(hints, dict):
            return dict(hints)
    except Exception:
        pass
    return dict(_TEMPLATE_ROUTING_HINTS.get(tid, {}))
