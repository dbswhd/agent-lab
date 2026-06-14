"""Structured envelope adapter — provider-agnostic request + parse helpers."""

from __future__ import annotations

import json
import os
from typing import Any

from agent_lab.agent_envelope import split_structured_envelope_prefix
from agent_lab.reply_policy import ReplyPolicy


def structured_envelope_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_STRUCTURED_ENVELOPE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def should_request_structured_envelope(policy: ReplyPolicy | None) -> bool:
    if not structured_envelope_enabled() or policy is None:
        return False
    return bool(policy.inject_envelope_guidance)


def structured_envelope_system_addon(*, compact: bool = False) -> str:
    if compact:
        return (
            "[Structured envelope]\n"
            'Line 1: JSON object {"act":"ENDORSE","refs":[],"confidence":0.9}\n'
            "Line 2+: human-readable body (markdown OK). Fence optional."
        )
    return (
        "[Structured envelope — machine layer first]\n"
        'Output line 1 as a single JSON object with required field "act":\n'
        '{"act":"ENDORSE","refs":[],"confidence":0.9}\n'
        "Then a blank line, then your normal readable reply for the Human.\n"
        "Valid acts: PROPOSE | AMEND | ENDORSE | CHALLENGE | PASS | BLOCK | MESSAGE\n"
        "Alternatively you may use ```agent-envelope fenced JSON (legacy)."
    )


def parse_claude_json_stdout(stdout: str) -> tuple[dict[str, Any] | None, str]:
    """Parse Claude CLI ``--output-format json`` wrapper; extract envelope if present."""
    raw = (stdout or "").strip()
    if not raw:
        return None, raw
    try:
        wrapper = json.loads(raw)
    except json.JSONDecodeError:
        return split_structured_envelope_prefix(raw)
    if not isinstance(wrapper, dict):
        return None, raw
    result = wrapper.get("result")
    if isinstance(result, str) and result.strip():
        structured, body = split_structured_envelope_prefix(result)
        if structured is not None:
            return structured, body or result
        return None, result.strip()
    return None, raw


def merge_structured_reply(
    text: str,
    *,
    provider_structured: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Combine provider-native structured envelope with prefix-in-text fallback."""
    if provider_structured and isinstance(provider_structured, dict):
        structured, prose = split_structured_envelope_prefix(text)
        return prose or text, provider_structured
    structured, prose = split_structured_envelope_prefix(text)
    if structured is not None:
        return prose or text, structured
    return text, None
