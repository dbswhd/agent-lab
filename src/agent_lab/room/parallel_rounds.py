"""Parallel and sequential agent round runners."""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from typing import Any, Literal

from agent_lab.run.state import RunStateLike

# Tasks where agents should run sequentially even in round 1.
# peer_review: architect → critic ordering is intentional (critic reads architect).
# cold_critic: single fresh-eyes agent; parallelism is meaningless.
TaskType = Literal["consensus", "peer_review", "discuss", "cold_critic"]
_SEQUENTIAL_TASK_TYPES: frozenset[str] = frozenset({"peer_review", "cold_critic"})

from agent_lab.core.context_bundle import ContextBundle
from agent_lab.room._typing import as_agent_id
from agent_lab.agents.registry import AgentId, available_agents
from agent_lab.room.turn_state import sync_run_meta_turn_state
from agent_lab.run.control import (
    RoomRunCancelled,
    check_cancelled,
    is_cancelled,
    terminate_active_children,
)
from agent_lab.room.messages import (
    ChatMessage,
    DEFAULT_AGENT_PARALLEL_ROUNDS,
    MAX_AGENT_PARALLEL_ROUNDS,
    MAX_AGENTS_PER_ROUND,
    OnAgentEvent,
    _human_turn_count,
    _round_agent_order,
    build_agent_context_bundle,
)

from agent_lab.room.agent_invoke import (
    _invoke_agent_for_round,
    _teammate_idle_peer_message,
)
from agent_lab.room.session_persist import _session_context, load_session_messages


def _collect_parallel_futures(executor: ThreadPoolExecutor, futures: set[Future[Any]]) -> list[Any]:
    """Collect agent futures; cooperative cancel must not block on slow siblings."""
    results: list[Any] = []
    pending = set(futures)
    try:
        while pending:
            check_cancelled()
            done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
            if not done:
                continue
            for fut in done:
                results.append(fut.result())
        return results
    except RoomRunCancelled:
        # Wait for in-flight agents to finish cooperative cancel (partial ChatMessage)
        # before killing subprocesses — otherwise streamed reply text is lost (issue D).
        deadline = time.monotonic() + 3.0
        while pending and time.monotonic() < deadline:
            done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            for fut in done:
                try:
                    results.append(fut.result())
                except Exception:
                    pass
        for fut in list(pending):
            if not fut.done():
                continue
            try:
                results.append(fut.result())
            except Exception:
                pass
        terminate_active_children()
        return results
    finally:
        if is_cancelled():
            executor.shutdown(wait=False, cancel_futures=True)
        else:
            executor.shutdown(wait=True, cancel_futures=False)


def run_parallel_round(
    topic: str,
    messages: list[ChatMessage],
    agents: list[AgentId] | None = None,
    *,
    parallel_round: int = 1,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    review_mode: bool = False,
    human_turn_index: int = 0,
    plan_md: str = "",
    run_meta: RunStateLike | None = None,
    context_log: list[dict[str, Any]] | None = None,
    efficiency_mode: bool = False,
    extra_follow_up: str = "",
    task_type: str | None = None,
) -> list[ChatMessage]:
    """Call selected agents for one round.

    Parallel vs sequential decision:
    - round >= 2 → always sequential (agents build on each other's replies)
    - task_type in _SEQUENTIAL_TASK_TYPES → sequential regardless of round number
    - otherwise round 1 → parallel (consensus, general discuss)
    """
    from agent_lab.room.agent_mentions import effective_invoke_agents

    invoke_ids = effective_invoke_agents(
        [str(a) for a in (agents or [])],
        run_meta,
        fallback=[str(a) for a in available_agents()],
    )
    active: list[AgentId] = [as_agent_id(a) for a in invoke_ids]
    if not active:
        raise RuntimeError("No agents available. Configure CURSOR_API_KEY, codex login, or claude login.")
    active = active[:MAX_AGENTS_PER_ROUND]
    ordered = _round_agent_order(
        active,
        review_mode=review_mode,
        parallel_round=parallel_round,
        run_meta=run_meta,
    )
    from agent_lab.role_plan import resolve_review_advocate

    _advocate = (
        resolve_review_advocate(
            [str(a) for a in ordered],
            human_turn_index,
            run_meta=run_meta,
            review_mode=review_mode,
        )
        if review_mode
        else None
    )
    review_advocate = as_agent_id(_advocate) if _advocate else None

    check_cancelled()
    from agent_lab.steer import drain_steer_follow_up

    steer_block = drain_steer_follow_up(run_meta=run_meta if isinstance(run_meta, dict) else None)
    if steer_block.strip():
        extra_follow_up = "\n\n".join(
            x for x in (extra_follow_up, steer_block) if x and x.strip()
        )

    replies: list[ChatMessage] = []
    sequential = parallel_round >= 2 or bool(task_type and task_type in _SEQUENTIAL_TASK_TYPES)
    from agent_lab.room.team_orchestration import lead_last_r1_enabled, team_r1_split

    want_lead_last = (
        not sequential and parallel_round == 1 and not review_mode and bool(run_meta) and lead_last_r1_enabled(run_meta)
    )
    parallel_batch, lead_tail = (
        team_r1_split([str(a) for a in ordered], run_meta) if want_lead_last else ([str(a) for a in ordered], [])
    )
    use_lead_last_r1 = want_lead_last and bool(lead_tail) and len(parallel_batch) < len(ordered)

    if use_lead_last_r1:
        check_cancelled()
        thread = list(messages)
        if parallel_batch:
            executor = ThreadPoolExecutor(max_workers=len(parallel_batch))
            futures = {
                executor.submit(
                    _invoke_agent_for_round,
                    as_agent_id(str(aid)),
                    topic=topic,
                    thread=messages,
                    parallel_round=parallel_round,
                    permissions=permissions,
                    review_mode=review_mode,
                    review_advocate=review_advocate,
                    plan_md=plan_md,
                    run_meta=run_meta,
                    on_event=on_event,
                    context_log=context_log,
                    efficiency_mode=efficiency_mode,
                    human_turn_index=human_turn_index,
                )
                for aid in parallel_batch
            }
            try:
                replies.extend(_collect_parallel_futures(executor, futures))
            except RoomRunCancelled:
                pass
            thread = list(messages) + replies
        for aid in lead_tail:
            check_cancelled()
            try:
                msg = _invoke_agent_for_round(
                    as_agent_id(str(aid)),
                    topic=topic,
                    thread=thread,
                    parallel_round=parallel_round,
                    permissions=permissions,
                    review_mode=review_mode,
                    review_advocate=review_advocate,
                    plan_md=plan_md,
                    run_meta=run_meta,
                    on_event=on_event,
                    context_log=context_log,
                    efficiency_mode=efficiency_mode,
                    human_turn_index=human_turn_index,
                )
                replies.append(msg)
                thread.append(msg)
                idle_peer = _teammate_idle_peer_message(as_agent_id(str(aid)), run_meta, parallel_round=parallel_round)
                if idle_peer:
                    replies.append(idle_peer)
                    thread.append(idle_peer)
            except RoomRunCancelled:
                break
        for aid in parallel_batch:
            idle_peer = _teammate_idle_peer_message(as_agent_id(str(aid)), run_meta, parallel_round=parallel_round)
            if idle_peer:
                replies.append(idle_peer)
        return replies

    if sequential:
        thread = list(messages)
        round_follow = ""
        if parallel_round >= 2:
            from agent_lab.reply_policy import (
                envelope_follow_up_block,
                resolve_reply_policy,
            )

            policy = resolve_reply_policy(
                parallel_round=parallel_round,
                review_mode=review_mode,
                consensus_mode=bool(run_meta and run_meta.get("_active_consensus")),
                turn_profile=str((run_meta or {}).get("turn_profile") or ""),
                efficiency_mode=efficiency_mode,
            )
            ctx = "review" if review_mode else "discuss"
            round_follow = envelope_follow_up_block(policy, context=ctx)
        if extra_follow_up.strip():
            round_follow = "\n\n".join(x for x in (round_follow, extra_follow_up) if x.strip())
        try:
            for aid in ordered:
                check_cancelled()
                msg = _invoke_agent_for_round(
                    aid,
                    topic=topic,
                    thread=thread,
                    parallel_round=parallel_round,
                    permissions=permissions,
                    review_mode=review_mode,
                    review_advocate=review_advocate,
                    plan_md=plan_md,
                    run_meta=run_meta,
                    on_event=on_event,
                    context_log=context_log,
                    extra_follow_up=round_follow,
                    efficiency_mode=efficiency_mode,
                    human_turn_index=human_turn_index,
                )
                replies.append(msg)
                thread.append(msg)
                idle_peer = _teammate_idle_peer_message(as_agent_id(str(aid)), run_meta, parallel_round=parallel_round)
                if idle_peer:
                    replies.append(idle_peer)
                    thread.append(idle_peer)
        except RoomRunCancelled:
            pass
        return replies

    executor = ThreadPoolExecutor(max_workers=len(ordered))
    futures = {
        executor.submit(
            _invoke_agent_for_round,
            as_agent_id(str(aid)),
            topic=topic,
            thread=messages,
            parallel_round=parallel_round,
            permissions=permissions,
            review_mode=review_mode,
            review_advocate=review_advocate,
            plan_md=plan_md,
            run_meta=run_meta,
            on_event=on_event,
            context_log=context_log,
            efficiency_mode=efficiency_mode,
            human_turn_index=human_turn_index,
        )
        for aid in ordered
    }
    try:
        replies.extend(_collect_parallel_futures(executor, futures))
    except RoomRunCancelled:
        pass
    for aid in ordered:
        idle_peer = _teammate_idle_peer_message(aid, run_meta, parallel_round=parallel_round)
        if idle_peer:
            replies.append(idle_peer)
    return replies


def run_agent_rounds(
    topic: str,
    messages: list[ChatMessage],
    *,
    agents: list[AgentId] | None = None,
    parallel_rounds: int = DEFAULT_AGENT_PARALLEL_ROUNDS,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    review_mode: bool = False,
    human_turn_index: int = 0,
    plan_md: str = "",
    run_meta: RunStateLike | None = None,
    context_log: list[dict[str, Any]] | None = None,
    efficiency_mode: bool = False,
) -> list[ChatMessage]:
    """Run multiple parallel waves; later waves see earlier agents' replies in the thread."""
    from agent_lab.room.agent_mentions import effective_invoke_agents
    from agent_lab.room.team_orchestration import normalize_turn_profile
    from agent_lab.room.turn_routing import prepare_turn_routing

    profile = normalize_turn_profile(run_meta.get("turn_profile") if run_meta else None)
    invoke_ids = effective_invoke_agents(
        [str(a) for a in (agents or [])],
        run_meta,
        fallback=[str(a) for a in available_agents()],
    )[:MAX_AGENTS_PER_ROUND]
    if run_meta is not None and invoke_ids:
        _routing = prepare_turn_routing(
            topic,
            run_meta,
            invoke_ids,
            agents=[str(a) for a in (agents or [])] if agents else None,
            efficiency_mode=efficiency_mode,
            min_agents=1,
            apply_subset=True,
            on_event=on_event,
        )
        invoke_ids = _routing.active
        profile = normalize_turn_profile(run_meta.get("turn_profile"))
    n = max(1, min(parallel_rounds, MAX_AGENT_PARALLEL_ROUNDS))
    if profile == "specialist" or str((run_meta or {}).get("_turn_topology") or "") == "producer_reviewer":
        n = max(n, 2)
    all_replies: list[ChatMessage] = []
    try:
        for r in range(1, n + 1):
            check_cancelled()
            if on_event:
                on_event("agent_round_start", {"round": r, "total": n})
            batch = run_parallel_round(
                topic,
                messages + all_replies,
                agents=agents,
                parallel_round=r,
                on_event=on_event,
                permissions=permissions,
                review_mode=review_mode,
                human_turn_index=human_turn_index,
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
            all_replies.extend(batch)
            sync_run_meta_turn_state(
                run_meta,
                messages + all_replies,
                active_agents=effective_invoke_agents(
                    [str(a) for a in (agents or [])],
                    run_meta,
                    fallback=[str(a) for a in available_agents()],
                )[:MAX_AGENTS_PER_ROUND],
                plan_md=plan_md,
            )
    except RoomRunCancelled:
        pass
    return all_replies


def preview_agent_payload(
    folder: Path,
    agent: AgentId,
    *,
    agents: list[AgentId] | None = None,
    parallel_round: int = 1,
    permissions: dict | None = None,
    review_mode: bool = False,
    efficiency_mode: bool = False,
    slim_context: bool = False,
) -> tuple[str, ContextBundle]:
    """Build agent context without calling an LLM. Returns (payload str, ContextBundle)."""
    if not folder.is_dir():
        raise FileNotFoundError(f"session not found: {folder}")
    topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
    messages = load_session_messages(folder)
    plan_md, run_meta = _session_context(folder)
    active = agents or available_agents()
    active = active[:MAX_AGENTS_PER_ROUND]
    human_turn_index = max(0, _human_turn_count(messages) - 1)
    from agent_lab.role_plan import resolve_review_advocate

    _advocate = (
        resolve_review_advocate(
            [str(a) for a in active],
            human_turn_index,
            run_meta=run_meta,
            review_mode=review_mode,
        )
        if review_mode
        else None
    )
    review_advocate = as_agent_id(_advocate) if _advocate else None
    bundle = build_agent_context_bundle(
        topic,
        messages,
        agent,
        permissions=permissions,
        parallel_round=parallel_round,
        review_mode=review_mode,
        review_advocate=review_advocate,
        plan_md=plan_md,
        run_meta=run_meta,
        efficiency_mode=efficiency_mode,
        slim_context=slim_context,
    )
    return bundle.render(), bundle
