from __future__ import annotations

"""Post-turn plan / scribe bridge helpers (F9)."""

import logging
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.room.messages import ChatMessage, OnAgentEvent
from agent_lab.room.plan_scribe import (
    _plan_trigger_for_turn,
    _plan_workflow_post_agent_turn,
)

log = logging.getLogger(__name__)


def _casual_turn_mode(synthesize: bool) -> str:
    from agent_lab.room.turn_policy import turn_policy_enabled

    if turn_policy_enabled():
        return "discuss"
    return "plan" if synthesize else "discuss"


def _post_agent_turn_plan(
    folder: Path,
    *,
    topic: str,
    messages: list[ChatMessage],
    run_meta: RunStateLike,
    plan_before: str,
    mode: str,
    synthesize: bool,
    cancelled: bool,
    active_agents: list[Any],
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    consensus_meta: dict[str, Any] | None,
    human_turn_num: int,
) -> tuple[str, bool, dict[str, Any], str | None]:
    from agent_lab.room.turn_policy import (
        TurnSignals,
        apply_turn_effects,
        count_proposed_tags_in_turn,
        turn_policy_enabled,
    )

    if turn_policy_enabled():
        result = apply_turn_effects(
            signals=TurnSignals.from_run_meta(
                run_meta,
                consensus_meta=consensus_meta,
                cancelled=cancelled,
                proposed_tags_count=count_proposed_tags_in_turn(messages),
            ),
            folder=folder,
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            plan_before=plan_before,
            mode=mode,
            cancelled=cancelled,
            active_agents=active_agents,
            permissions=permissions,
            on_event=on_event,
            consensus_meta=consensus_meta,
            human_turn=human_turn_num,
        )
        return result.plan_md, result.scribe_applied, result.run_meta, result.plan_trigger

    plan_md, scribe_applied, run_meta = _plan_workflow_post_agent_turn(
        folder,
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        plan_before=plan_before,
        mode=mode,
        synthesize=synthesize,
        cancelled=cancelled,
        active_agents=active_agents,
        permissions=permissions,
        on_event=on_event,
    )
    plan_trigger = _plan_trigger_for_turn(synthesize=synthesize, scribe_applied=scribe_applied)
    return plan_md, scribe_applied, run_meta, plan_trigger


def _post_agent_turn_plan_with_fail_banner(
    folder: Path,
    *,
    topic: str,
    messages: list[ChatMessage],
    run_meta: RunStateLike,
    plan_before: str,
    mode: str,
    synthesize: bool,
    cancelled: bool,
    active_agents: list[Any],
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    consensus_meta: dict[str, Any] | None,
    human_turn_num: int,
) -> tuple[str, bool, dict[str, Any], str | None]:
    plan_md, scribe_applied, run_meta, plan_trigger = _post_agent_turn_plan(
        folder,
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        plan_before=plan_before,
        mode=mode,
        synthesize=synthesize,
        cancelled=cancelled,
        active_agents=active_agents,
        permissions=permissions,
        on_event=on_event,
        consensus_meta=consensus_meta,
        human_turn_num=human_turn_num,
    )
    if synthesize and scribe_applied and not plan_md:
        plan_md = "## Plan synthesis failed\n\nunknown error"
    return plan_md, scribe_applied, run_meta, plan_trigger
