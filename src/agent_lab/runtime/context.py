"""Runtime context helpers — prompt enrichment without phase transitions."""

from __future__ import annotations

from pathlib import Path

from agent_lab.run.state import RunStateLike


def enrich_execute_prompt(
    user: str,
    run_meta: RunStateLike | None,
    *,
    session_folder: Path | None = None,
) -> str:
    """Append mission wisdom + drained Human steer notes to execute/repair prompts."""
    from agent_lab.mission.notepad import inject_wisdom_into_prompt
    from agent_lab.steer import drain_steer_follow_up

    enriched = inject_wisdom_into_prompt(user, run_meta)
    meta = run_meta if isinstance(run_meta, dict) else None
    steer = drain_steer_follow_up(
        session_folder,
        meta,
        target="execute",
    )
    if not steer.strip():
        return enriched
    return f"{enriched.rstrip()}\n\n{steer.strip()}"


def build_mission_wisdom_block(
    run_meta: RunStateLike | None,
    *,
    max_chars: int = 1500,
) -> str:
    """Mission notepad tails for agent context bundles."""
    from agent_lab.mission.notepad import build_mission_wisdom_block as _build

    return _build(run_meta, max_chars=max_chars)
