"""Clarity gate for the CLARIFY phase (AGENT_LAB_PIPELINE).

Concrete-anchor signal detection (deterministic; mirrors the ralplan-gate idea) plus a
dedicated single-agent ambiguity scorer that is intentionally separate from the multi-agent
Room. Anchored tasks skip CLARIFY; genuinely vague tasks are scored and held in CLARIFY until
ambiguity drops to/below the threshold.
"""
from __future__ import annotations

import os
import re
from typing import Any

# Default ambiguity threshold; override via AGENT_LAB_CLARITY_THRESHOLD.
CLARITY_AMBIGUITY_THRESHOLD = 0.30

_ANCHOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[\w./-]+\.[A-Za-z]{1,6}\b"),            # file path with extension
    re.compile(r"#\d+"),                                  # issue / PR number
    re.compile(r"\b[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*\b"),   # camelCase
    re.compile(r"\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b"),   # PascalCase
    re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b"),              # snake_case
    re.compile(r"(?i)acceptance criteria"),
    re.compile(r"```"),                                   # code block
)

_SCORE_SYSTEM = (
    "You are an ambiguity scorer. Given a development task, return a single float between "
    "0.0 (perfectly clear, ready to build) and 1.0 (utterly vague). Reply with ONLY the number."
)


def _threshold() -> float:
    raw = os.getenv("AGENT_LAB_CLARITY_THRESHOLD", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return CLARITY_AMBIGUITY_THRESHOLD


def detect_concrete_anchors(text: str) -> bool:
    """True when the task carries a concrete anchor (file/symbol/issue/criteria/code block)."""
    return any(pattern.search(text or "") for pattern in _ANCHOR_PATTERNS)


def _mission_clarity_text(run: dict[str, Any]) -> str:
    loop = run.get("verified_loop")
    loop = loop if isinstance(loop, dict) else {}
    goal = loop.get("loop_goal")
    goal = goal if isinstance(goal, dict) else {}
    ml = run.get("mission_loop")
    ml = ml if isinstance(ml, dict) else {}
    parts = [goal.get("text"), run.get("topic"), ml.get("clarify_task")]
    return " ".join(str(p) for p in parts if p).strip()


def _parse_score(reply: str) -> float:
    match = re.search(r"(0(?:\.\d+)?|1(?:\.0+)?)", reply or "")
    if not match:
        return 0.8  # conservative: unparseable => needs clarification
    try:
        return max(0.0, min(1.0, float(match.group(1))))
    except ValueError:
        return 0.8


def score_ambiguity(text: str) -> float:
    """Dedicated single-agent ambiguity score in [0,1]; mock-safe deterministic fallback."""
    text = (text or "").strip()
    if not text:
        return 1.0
    if detect_concrete_anchors(text):
        return 0.0
    from agent_lab.agents.registry import _mock_agents_enabled

    if _mock_agents_enabled():
        # Deterministic, reproducible for tests / mock runs: no concrete anchor => vague.
        return 0.8
    from agent_lab.agents.registry import available_agents, call_agent

    agents = available_agents()
    if not agents:
        return 0.8  # no dedicated scorer available => conservative needs-clarification
    reply = call_agent(agents[0], _SCORE_SYSTEM, f"Task:\n{text}\n\nAmbiguity score (0.0-1.0):")
    return _parse_score(reply)


def clarity_threshold_met(run: dict[str, Any]) -> bool:
    """CLARIFY may pass to DISCUSS when concrete anchors exist OR ambiguity <= threshold."""
    text = _mission_clarity_text(run)
    if detect_concrete_anchors(text):
        return True
    return score_ambiguity(text) <= _threshold()
