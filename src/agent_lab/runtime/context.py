"""Runtime context helpers — prompt enrichment without phase transitions."""

from __future__ import annotations

from typing import Any


def enrich_execute_prompt(user: str, run_meta: dict[str, Any] | None) -> str:
    """Append mission wisdom block to execute/repair user prompts."""
    from agent_lab.mission_loop import inject_wisdom_into_prompt

    return inject_wisdom_into_prompt(user, run_meta)


def build_mission_wisdom_block(
    run_meta: dict[str, Any] | None,
    *,
    max_chars: int = 1500,
) -> str:
    """Mission notepad tails for agent context bundles."""
    from agent_lab.mission_loop import build_mission_wisdom_block as _build

    return _build(run_meta, max_chars=max_chars)
