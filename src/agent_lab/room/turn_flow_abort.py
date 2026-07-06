from __future__ import annotations

"""Turn abort helpers when @-mention roster validation fails (F9)."""

from pathlib import Path
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.room.messages import ChatMessage, OnAgentEvent
from agent_lab.room.session_persist import _write_session_files
from agent_lab.room.turn_flow_support import _checkpoint_chat, emit_mention_roster_error
from agent_lab.room.turn_meta import _delegate_run_meta_patch, _turn_snapshot

def _abort_mention_roster_error(
    folder: Path | None,
    *,
    topic: str,
    messages: list[ChatMessage],
    plan_md: str,
    run_meta: RunStateLike,
    active_agents: list[Any],
    mode: str,
    synthesize: bool,
    on_event: OnAgentEvent | None,
    message: str,
    permissions: dict | None,
    turn_profile: str | None,
) -> tuple[list[ChatMessage], str]:
    """Persist a failed turn when explicit @-mentions are outside the session roster."""
    from agent_lab.room.turn_flow_support import emit_mention_roster_error

    emit_mention_roster_error(on_event, message)
    messages.append(
        ChatMessage(role="system", agent=None, content=message, visibility="human"),
    )
    _checkpoint_chat(folder, messages, topic=topic)
    if folder is not None and folder.is_dir():
        _write_session_files(
            folder,
            topic,
            messages,
            plan_md,
            agents_used=[str(a) for a in active_agents],
            merge_meta={"topic": topic},
            turn_meta=_turn_snapshot(
                mode=mode,
                synthesize=synthesize,
                agents_used=[str(a) for a in active_agents],
                parallel_rounds=0,
                permissions=permissions,
                latency_ms=0,
                status="failed",
                turn_profile=turn_profile,
                failed_agents=[],
                succeeded_agents=[],
            ),
            run_meta_patch=_delegate_run_meta_patch(run_meta),
        )
    return messages, plan_md
