"""Turn setup: profile flags and server clarifier interview."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.room.messages import OnAgentEvent


def apply_turn_profile_flags(
    run_meta: dict[str, Any],
    turn_profile: str | None,
    *,
    synthesize: bool,
    folder: Path | None,
    parallel_rounds: int,
    research_mode: bool,
) -> int:
    from agent_lab.run.meta import stamp_run_meta

    if turn_profile:
        tp = (turn_profile or "analyze").strip().lower()
        profile = "analyze" if tp == "discuss" else tp
        stamp_run_meta(run_meta, turn_profile=profile)
        if profile == "specialist":
            parallel_rounds = max(parallel_rounds, 2)
            if not run_meta.get("agent_capabilities_custom"):
                from agent_lab.room.agent_capabilities import ensure_specialist_capabilities

                ensure_specialist_capabilities(run_meta)
        from agent_lab.plan.workflow import apply_legacy_verified_turn_profile

        apply_legacy_verified_turn_profile(folder, run_meta, synthesize=synthesize)
    if research_mode or run_meta.get("turn_profile") == "specialist":
        stamp_run_meta(run_meta, research_mode=True)
    return parallel_rounds


def prepare_clarifier_for_turn(
    folder: Path | None,
    body: str,
    *,
    is_new_session: bool,
    human_turn_num: int,
    synthesize: bool,
    skip_server_clarifier: bool,
    on_event: OnAgentEvent | None,
) -> list[str] | None:
    if skip_server_clarifier:
        return None
    from agent_lab.session.clarifier import (
        build_clarifier_interview,
        interview_prompts,
        persist_clarifier_interview,
    )

    clarifier_interview = build_clarifier_interview(
        body,
        is_new_session=is_new_session,
        human_message_count=human_turn_num,
        plan_mode=synthesize,
    )
    if clarifier_interview and folder is not None:
        persisted = persist_clarifier_interview(folder, clarifier_interview)
        clarifier_interview = persisted.get("interview") or clarifier_interview
    clarifier_questions = interview_prompts(clarifier_interview)
    if clarifier_questions and on_event:
        on_event(
            "clarifier_prompt",
            {"questions": clarifier_questions, "interview": clarifier_interview},
        )
    return clarifier_questions
