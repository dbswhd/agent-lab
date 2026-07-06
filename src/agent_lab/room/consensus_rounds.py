"""Consensus-mode multi-round agent orchestration."""

from __future__ import annotations

from agent_lab.room._typing import agent_label, as_agent_id, as_agent_ids
from typing import Any

from agent_lab.run.state import RunStateLike

from agent_lab.agents.registry import AgentId, available_agents
from agent_lab.room.consensus import (
    consensus_follow_up,
    consensus_reply_verdict,
    debate_review_round,
    is_substantive_reply,
    pick_anchor,
    recombination_follow_up,
)
from agent_lab.room.turn_state import sync_run_meta_turn_state
from agent_lab.run.control import RoomRunCancelled, check_cancelled
from agent_lab.room.messages import (
    ChatMessage,
    MAX_AGENTS_PER_ROUND,
    OnAgentEvent,
    _agent_turn_failed,
    _current_turn_messages,
    _distinct_substantive_proposers,
    _human_turn_number,
    _is_agent_error_message,
    _is_valid_synthesis,
)

from agent_lab.room.agent_invoke import (
    _invoke_agent_for_round,
)
from agent_lab.room.parallel_rounds import run_parallel_round
from agent_lab.consensus_policy import ConsensusPolicy, default_consensus_policy


def run_consensus_agent_rounds(
    topic: str,
    messages: list[ChatMessage],
    *,
    agents: list[AgentId] | None = None,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    human_turn_index: int = 0,
    plan_md: str = "",
    run_meta: RunStateLike | None = None,
    context_log: list[dict[str, Any]] | None = None,
    efficiency_mode: bool = False,
    consensus_policy: ConsensusPolicy | None = None,
) -> tuple[list[ChatMessage], dict[str, Any] | None]:
    """자유 토론: R1 병렬 후 앵커 제안에 전원 「이의 없습니다」까지 순차 반복."""
    policy = consensus_policy or default_consensus_policy()
    from agent_lab.room.agent_mentions import effective_invoke_agents
    from agent_lab.topic_router import (
        batch_escalation_act,
        escalate_route,
        resolve_topic_route,
        route_debate_last,
    )

    invoke_ids = effective_invoke_agents(
        [str(a) for a in (agents or [])],
        run_meta,
        fallback=[str(a) for a in available_agents()],
    )[:MAX_AGENTS_PER_ROUND]
    active: list[AgentId] = [as_agent_id(a) for a in invoke_ids]
    if not active:
        raise RuntimeError("No agents available.")

    all_replies: list[ChatMessage] = []
    calls = 0
    if run_meta is not None:
        from agent_lab.room.turn_routing import bootstrap_turn_route

        route = bootstrap_turn_route(topic, run_meta, efficiency_mode=efficiency_mode)
    else:
        route = resolve_topic_route(
            topic,
            turn_profile="",
            session_template="",
            efficiency_mode=efficiency_mode,
        )
    cap_rounds, cap_calls = route.max_rounds, route.max_calls

    # Model Policy:
    # agents_within_cost_tier는 전원 필터될 때 원본을 반환하므로 안전하다.
    from agent_lab.model_policy import agents_within_cost_tier, preferred_cost_tier_for_category
    from agent_lab.trust_budget import budget_agent_tier_cap

    _category_tier = preferred_cost_tier_for_category(route.category)
    _budget_tier = budget_agent_tier_cap(run_meta)
    _tier_rank: dict[str, int] = {"low": 0, "medium": 1, "high": 2}
    _effective_tier: str | None = None
    for _t in (_category_tier, _budget_tier):
        if _t is not None:
            if _effective_tier is None or _tier_rank.get(_t, 2) < _tier_rank.get(_effective_tier, 2):
                _effective_tier = _t
    if _effective_tier is not None:
        _filtered = agents_within_cost_tier([str(a) for a in active], _effective_tier)  # type: ignore[arg-type]
        _filtered_set = set(_filtered)
        _policy_active = [a for a in active if str(a) in _filtered_set]
        # 합의 루프에서는 최소 2명이 필요하므로 1명 이하로 줄면 비용 상한을 적용하지 않는다.
        if len(_policy_active) >= 2 and _policy_active != active:
            active = _policy_active
            if on_event:
                on_event(
                    "model_policy_applied",
                    {
                        "effective_tier": _effective_tier,
                        "category_tier": _category_tier,
                        "budget_tier": _budget_tier,
                        "active": [str(a) for a in active],
                        "message": (
                            f"Model Policy — 비용 상한 {_effective_tier}: "
                            f"{', '.join(str(a) for a in active)} 참여."
                        ),
                    },
                )

    from agent_lab.turn_modes import apply_loop_budget_caps, loop_token_budget_exceeded

    cap_rounds, cap_calls = apply_loop_budget_caps(run_meta, cap_rounds, cap_calls)

    _routing_hint = None
    if run_meta is not None:
        from agent_lab.room.turn_routing import finalize_turn_routing

        _routing = finalize_turn_routing(
            route,
            run_meta,
            [str(a) for a in active],
            topic=topic,
            agents=[str(a) for a in (agents or [])] if agents else None,
            min_agents=2,
            apply_subset=True,
            on_event=on_event,
        )
        route = _routing.route
        active = as_agent_ids(_routing.active)

    def _harvest_discuss_objections(thread: list[ChatMessage]) -> None:
        """충돌을 상태로 — discuss CHALLENGE/BLOCK을 run.json objections에 등록 (P3)."""
        if run_meta is None:
            return
        from agent_lab.room.objections import harvest_objections_from_turn

        harvest_objections_from_turn(
            run_meta,
            thread,
            human_turn=_human_turn_number(human_turn_index),
            mode="discuss",
        )

    def _maybe_escalate(batch_msgs: list[ChatMessage]) -> None:
        """충돌 act → 카테고리 1단계 상승 (예산만 늘림, 강등 없음).

        에스컬레이션 시 agent_subset과 _turn_roles가 해제되어 전원 자유토론으로 복귀한다.
        """
        nonlocal route, cap_rounds, cap_calls, active
        act = batch_escalation_act(batch_msgs)
        if not act:
            return
        prev_subset = route.agent_subset
        prev_roles = dict((run_meta or {}).get("_turn_roles") or {})
        escalated = escalate_route(route, act=act, efficiency_mode=efficiency_mode)
        if escalated.category == route.category:
            return
        route = escalated
        cap_rounds, cap_calls = route.max_rounds, route.max_calls
        # 에스컬레이션 시 subset 해제 → 전체 에이전트로 복원
        if prev_subset and route.agent_subset is None:
            full = list(agents or available_agents())[:MAX_AGENTS_PER_ROUND]
            if len(full) > len(active):
                active = full
        if run_meta is not None:
            from agent_lab.room.turn_routing import refresh_routing_after_escalation

            route = refresh_routing_after_escalation(
                route,
                run_meta,
                [str(a) for a in active],
                topic=topic,
            )
            from agent_lab.inbox.harvest import record_escalation_harvest_keys

            record_escalation_harvest_keys(run_meta, batch_msgs, act=act)
        if on_event:
            on_event(
                "category_escalated",
                {
                    "from": route.escalated_from,
                    "to": route.category,
                    "act": route.escalation_act,
                    "subset_released": prev_subset is not None and route.agent_subset is None,
                    "roles_released": bool(prev_roles),
                    "message": f"{route.escalation_act} 발생 — 토픽 카테고리를 "
                    f"{route.escalated_from}→{route.category}로 승격합니다.",
                },
            )

    try:
        check_cancelled()
        if on_event:
            on_event(
                "agent_round_start",
                {"round": 1, "total": cap_rounds, "consensus": True},
            )
        batch = run_parallel_round(
            topic,
            messages,
            agents=active,
            parallel_round=1,
            on_event=on_event,
            permissions=permissions,
            review_mode=False,
            human_turn_index=human_turn_index,
            plan_md=plan_md,
            run_meta=run_meta,
            context_log=context_log,
            efficiency_mode=efficiency_mode,
            task_type="consensus",
        )
        all_replies.extend(batch)
        calls += len(batch)

        if _agent_turn_failed(batch):
            if on_event:
                on_event(
                    "consensus_incomplete",
                    {
                        "reason": "agent_error",
                        "message": "에이전트 호출 실패 — 합의를 기록하지 않습니다.",
                    },
                )
            return all_replies, {
                "status": "failed",
                "reason": "agent_error",
                "rounds": 1,
                "calls": calls,
            }

        working = messages + all_replies
        _maybe_escalate(batch)
        _harvest_discuss_objections(working)
        sync_run_meta_turn_state(
            run_meta,
            working,
            active_agents=active,
            plan_md=plan_md,
        )

        if len(active) < 2:
            return all_replies, None

        working = messages + all_replies
        last_debate = route_debate_last(route)
        r = 2
        while r <= last_debate:
            if calls >= cap_calls:
                break
            check_cancelled()
            review = debate_review_round(r)
            if on_event:
                on_event(
                    "agent_round_start",
                    {
                        "round": r,
                        "total": cap_rounds,
                        "consensus": True,
                        "debate": True,
                        "review_mode": review,
                    },
                )
            batch = run_parallel_round(
                topic,
                working,
                agents=active,
                parallel_round=r,
                on_event=on_event,
                permissions=permissions,
                review_mode=review,
                human_turn_index=human_turn_index,
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
            all_replies.extend(batch)
            calls += len(batch)
            working = messages + all_replies
            _maybe_escalate(batch)
            _harvest_discuss_objections(working)
            last_debate = route_debate_last(route)
            sync_run_meta_turn_state(
                run_meta,
                working,
                active_agents=active,
                plan_md=plan_md,
            )
            if r >= 2:
                from agent_lab.debate_convergence import (
                    debate_convergence_gate_enabled,
                    record_debate_convergence,
                    score_debate_convergence,
                    should_advance_debate,
                )

                if debate_convergence_gate_enabled():
                    conv = score_debate_convergence(
                        working,
                        active_agents=[str(a) for a in active],
                        run_meta=run_meta,
                        human_turn=_human_turn_number(human_turn_index),
                        phase="debate",
                    )
                    record_debate_convergence(run_meta, conv)
                    advance, advance_reason = should_advance_debate(
                        conv,
                        run_meta,
                        human_turn=_human_turn_number(human_turn_index),
                        debate_round=r,
                    )
                    if advance:
                        if on_event:
                            on_event(
                                "debate_convergence",
                                {
                                    "round": r,
                                    "convergence": conv.get("convergence"),
                                    "threshold": conv.get("threshold"),
                                    "weakest": conv.get("weakest"),
                                    "reason": advance_reason,
                                    "message": (
                                        f"Debate 수렴 {conv.get('convergence')} "
                                        f"(≥ {conv.get('threshold')}) — 토론 라운드 조기 종료."
                                    ),
                                },
                            )
                        last_debate = r
                        break
            if _agent_turn_failed(batch):
                if on_event:
                    on_event(
                        "consensus_incomplete",
                        {
                            "reason": "agent_error",
                            "message": "토론 루프 중 에이전트 실패 — 합의를 기록하지 않습니다.",
                        },
                    )
                return all_replies, {
                    "status": "failed",
                    "reason": "agent_error",
                    "rounds": r,
                    "calls": calls,
                }
            if run_meta is not None:
                from agent_lab.inbox.harvest import harvest_and_check_pause

                if harvest_and_check_pause(
                    run_meta,
                    working,
                    human_turn=_human_turn_number(human_turn_index),
                    plan_md=plan_md,
                    mode="discuss",
                    session_id=str(run_meta.get("_session_id") or "") or None,
                ):
                    if on_event:
                        on_event(
                            "inbox_pause",
                            {
                                "round": r,
                                "message": "Human Inbox 질문 대기 — 토론 라운드를 일시 중단합니다.",
                            },
                        )
                    return all_replies, {
                        "status": "paused",
                        "reason": "inbox_pending",
                        "rounds": r,
                        "calls": calls,
                    }
            r += 1

        # P3 품질 게이트 판정은 debate 시점 충돌만 본다 (재조합 합성 act 제외).
        debate_conflicts = sum(
            1
            if isinstance(env := getattr(m, "envelope", None), dict)
            and str(env.get("act") or "").upper() in ("CHALLENGE", "BLOCK", "AMEND")
            else 0
            for m in all_replies
        )

        # P4 재조합 라운드 — debate 종료 → pick_anchor 사이의 명시적 합성(crossover).
        recomb_meta: dict[str, Any] | None = None
        recomb_rounds = 0
        if route.recombination != "off" and len(active) >= 2:
            skip_reason = ""
            substantive_proposers = _distinct_substantive_proposers(all_replies)
            turn_state = (run_meta or {}).get("turn_state")
            consensus_status = (
                str(turn_state.get("consensus_status"))
                if isinstance(turn_state, dict) and turn_state.get("consensus_status")
                else None
            )
            policy_skip, policy_reason = policy.should_skip_recombination(
                consensus_status=consensus_status,
                substantive_proposers=substantive_proposers,
                rounds=debate_conflicts,
            )
            if policy_skip:
                skip_reason = policy_reason or "policy"
                if skip_reason == "insufficient_proposers" and substantive_proposers < 2:
                    skip_reason = "single_proposer"
            elif calls + len(active) > cap_calls:
                skip_reason = "cap"
            elif route.recombination == "auto":
                if efficiency_mode:
                    skip_reason = "efficiency"
                elif _distinct_substantive_proposers(all_replies) < 2:
                    skip_reason = "single_proposer"
            if skip_reason:
                recomb_meta = {"skipped": skip_reason}
            else:
                check_cancelled()
                recomb_round_no = last_debate + 1
                recomb_rounds = 1
                if on_event:
                    on_event(
                        "recombination_round_start",
                        {
                            "round": recomb_round_no,
                            "category": route.category,
                            "message": "재조합 라운드 — 서로의 제안을 결합한 합성안을 요청합니다.",
                        },
                    )
                batch = run_parallel_round(
                    topic,
                    working,
                    agents=active,
                    parallel_round=recomb_round_no,
                    on_event=on_event,
                    permissions=permissions,
                    review_mode=False,
                    human_turn_index=human_turn_index,
                    plan_md=plan_md,
                    run_meta=run_meta,
                    context_log=context_log,
                    efficiency_mode=efficiency_mode,
                    extra_follow_up=recombination_follow_up(),
                )
                all_replies.extend(batch)
                calls += len(batch)
                working = messages + all_replies
                if _agent_turn_failed(batch):
                    if on_event:
                        on_event(
                            "consensus_incomplete",
                            {
                                "reason": "agent_error",
                                "message": "재조합 라운드 실패 — 합의를 기록하지 않습니다.",
                            },
                        )
                    return all_replies, {
                        "status": "failed",
                        "reason": "agent_error",
                        "rounds": recomb_round_no,
                        "calls": calls,
                    }
                _harvest_discuss_objections(working)
                valid_syntheses = sum(1 for m in batch if _is_valid_synthesis(m, working))
                recomb_meta = {
                    "round": recomb_round_no,
                    "replies": len(batch),
                    "valid_syntheses": valid_syntheses,
                }
                sync_run_meta_turn_state(
                    run_meta,
                    working,
                    active_agents=active,
                    plan_md=plan_md,
                )

        quality: dict[str, Any] = {
            "debate_challenges": debate_conflicts,
            "forced_review": False,
            "category": route.category,
        }
        if run_meta is not None and run_meta.get("_debate_convergence"):
            quality["debate_convergence"] = run_meta.get("_debate_convergence")
        forced_review_rounds = 0
        from agent_lab.turn_modes import antidrift_enabled

        # Anti-drift B (panel-only by construction: this path runs only under consensus_mode):
        # immediate 0-objection unanimity forces exactly one red-team round even when the route's
        # own quality gate is off. Respects the same caps; never touches the approval spine.
        antidrift_redteam = antidrift_enabled() and not route.quality_gate
        if (
            (route.quality_gate or antidrift_redteam)
            and debate_conflicts == 0
            and len(active) >= 2
            and calls < cap_calls
        ):
            check_cancelled()
            from agent_lab.role_plan import resolve_review_advocate

            advocate = resolve_review_advocate(
                [str(a) for a in active],
                human_turn_index,
                run_meta=run_meta,
                review_mode=True,
            )
            quality["forced_review"] = True
            quality["advocate"] = str(advocate) if advocate else ""
            if antidrift_redteam:
                quality["antidrift_redteam"] = True
            forced_review_rounds = 1
            advocate_id = as_agent_id(str(advocate)) if advocate else active[0]
            if on_event:
                on_event(
                    "quality_gate_review",
                    {
                        "agent": str(advocate_id),
                        "category": route.category,
                        "round": last_debate + 1 + recomb_rounds,
                        "message": (
                            f"{agent_label(advocate_id)}에게 합의 전 강제 반론 라운드를 요청합니다 "
                            f"(토론 무충돌 · {route.category})."
                        ),
                    },
                )
            review_msg = _invoke_agent_for_round(
                advocate_id,
                topic=topic,
                thread=working,
                parallel_round=last_debate + 1 + recomb_rounds,
                permissions=permissions,
                review_mode=True,
                review_advocate=advocate_id,
                plan_md=plan_md,
                run_meta=run_meta,
                on_event=on_event,
                context_log=context_log,
                extra_follow_up=(
                    "[품질 게이트 — 강제 반론] 이번 토론은 이견 없이 수렴했습니다. "
                    "합의 확정 전 점검으로, 지금까지의 제안에서 가장 약한 가정이나 "
                    "누락된 리스크 1건을 골라 CHALLENGE 또는 AMEND envelope로 "
                    "실질적 반론·대안을 제시하세요. 형식적 반론은 금지 — 정말 "
                    "반론이 없으면 그 근거를 한 줄로 밝히고 ENDORSE 하세요."
                ),
                efficiency_mode=efficiency_mode,
                slim_context=efficiency_mode,
                human_turn_index=human_turn_index,
            )
            all_replies.append(review_msg)
            calls += 1
            working = messages + all_replies
            if _is_agent_error_message(review_msg):
                if on_event:
                    on_event(
                        "consensus_incomplete",
                        {
                            "reason": "agent_error",
                            "agent": advocate,
                            "message": "품질 게이트 라운드 실패 — 합의를 기록하지 않습니다.",
                        },
                    )
                return all_replies, {
                    "status": "failed",
                    "reason": "agent_error",
                    "agent": advocate,
                    "rounds": last_debate + 1 + recomb_rounds,
                    "calls": calls,
                    "quality": quality,
                }
            review_env = getattr(review_msg, "envelope", None)
            review_act = str(review_env.get("act") or "").upper() if isinstance(review_env, dict) else ""
            if review_act in ("CHALLENGE", "BLOCK", "AMEND"):
                quality["forced_review_act"] = review_act
            _maybe_escalate([review_msg])
            _harvest_discuss_objections(working)
            sync_run_meta_turn_state(
                run_meta,
                working,
                active_agents=active,
                plan_md=plan_md,
            )

        anchor_seq = 0
        human_turn_no = _human_turn_number(human_turn_index)

        def _next_anchor_id() -> str:
            nonlocal anchor_seq
            anchor_seq += 1
            return f"a{human_turn_no}-{anchor_seq}"

        anchor = pick_anchor(_current_turn_messages(working), active, anchor_id=_next_anchor_id())
        if not anchor:
            if on_event:
                on_event(
                    "consensus_incomplete",
                    {
                        "reason": "no_anchor",
                        "message": "실질 제안이 없어 합의 확인을 건너뜁니다.",
                    },
                )
            return all_replies, None

        anchor_lineage: list[dict[str, Any]] = [anchor.to_dict()]
        anchor_delta = ""
        pending: set[AgentId] = {a for a in active if a != anchor.agent}
        consented: list[str] = []
        parallel_round = last_debate + 1 + recomb_rounds + forced_review_rounds
        sync_run_meta_turn_state(
            run_meta,
            working,
            active_agents=active,
            consensus={
                "status": "open",
                "anchor": anchor.to_dict(),
                "pending_agents": sorted(pending),
            },
            plan_md=plan_md,
            pending_agents=sorted(pending),
        )

        while pending and parallel_round <= cap_rounds and calls < cap_calls:
            check_cancelled()
            if loop_token_budget_exceeded(run_meta, context_log or []):
                if on_event:
                    on_event(
                        "consensus_incomplete",
                        {
                            "reason": "loop_token_budget",
                            "message": "Loop token budget reached — consensus paused.",
                        },
                    )
                break
            if on_event:
                on_event(
                    "agent_round_start",
                    {
                        "round": parallel_round,
                        "total": cap_rounds,
                        "consensus": True,
                    },
                )
            thread = list(messages) + list(all_replies)
            from agent_lab.room.tasks import open_tasks_for_consensus

            open_tasks = open_tasks_for_consensus(run_meta)
            task_refs = [str(t.get("id") or "") for t in open_tasks if t.get("id")]
            follow = consensus_follow_up(
                anchor,
                open_task_refs=task_refs or None,
                amend_delta=anchor_delta,
            )
            for aid in [a for a in active if a in pending]:
                if calls >= cap_calls:
                    break
                check_cancelled()
                msg = _invoke_agent_for_round(
                    aid,
                    topic=topic,
                    thread=thread,
                    parallel_round=parallel_round,
                    permissions=permissions,
                    review_mode=False,
                    review_advocate=None,
                    plan_md=plan_md,
                    run_meta=run_meta,
                    on_event=on_event,
                    context_log=context_log,
                    extra_follow_up=follow,
                    efficiency_mode=efficiency_mode,
                    slim_context=efficiency_mode,
                    human_turn_index=human_turn_index,
                )
                all_replies.append(msg)
                thread.append(msg)
                calls += 1
                if _is_agent_error_message(msg):
                    if on_event:
                        on_event(
                            "consensus_incomplete",
                            {
                                "reason": "agent_error",
                                "agent": aid,
                                "message": "에이전트 호출 실패 — ENDORSE 합의를 중단합니다.",
                            },
                        )
                    meta = {
                        "status": "failed",
                        "reason": "agent_error",
                        "agent": aid,
                        "anchor": anchor.to_dict(),
                        "rounds": parallel_round,
                        "calls": calls,
                    }
                    sync_run_meta_turn_state(
                        run_meta,
                        thread,
                        active_agents=active,
                        consensus=meta,
                        plan_md=plan_md,
                    )
                    return all_replies, meta
                text = msg.content or ""
                verdict = consensus_reply_verdict(text, msg.envelope)
                _maybe_escalate([msg])
                _harvest_discuss_objections(thread)
                if verdict in ("endorse", "pass"):
                    pending.discard(aid)
                    consented.append(aid)
                    if run_meta is not None:
                        from agent_lab.room.objections import (
                            resolve_objections_on_endorse,
                        )

                        resolve_objections_on_endorse(
                            run_meta,
                            str(aid),
                            human_turn=_human_turn_number(human_turn_index),
                        )
                elif verdict == "substantive" or is_substantive_reply(text, msg.envelope):
                    new_anchor = pick_anchor(
                        _current_turn_messages(thread),
                        active,
                        anchor_id=_next_anchor_id(),
                        prev_anchor=anchor,
                    )
                    if new_anchor:
                        # 변경점 1줄 delta — 구 텍스트 동의 ≠ 새 텍스트 동의이므로
                        # 하드 리셋은 유지하되 재확인 비용을 압축한다 (P4).
                        anchor_delta = f"직전 앵커({anchor.id}) 「{anchor.excerpt[:100]}」를 보완·대체한 수정안입니다."
                        anchor = new_anchor
                        anchor_lineage.append(anchor.to_dict())
                        pending = {a for a in active if a != anchor.agent}
                        consented = []
                    else:
                        pending.discard(aid)

                sync_run_meta_turn_state(
                    run_meta,
                    thread,
                    active_agents=active,
                    consensus={
                        "status": "open",
                        "anchor": anchor.to_dict(),
                        "pending_agents": sorted(pending),
                        "agents_consented": consented,
                    },
                    plan_md=plan_md,
                    pending_agents=sorted(pending),
                )

            from agent_lab.debate_convergence import (
                debate_convergence_gate_enabled,
                record_debate_convergence,
                score_debate_convergence,
            )

            convergence_result = None
            if debate_convergence_gate_enabled():
                thread_for_score = list(messages) + list(all_replies)
                convergence_result = score_debate_convergence(
                    thread_for_score,
                    active_agents=[str(a) for a in active],
                    run_meta=run_meta,
                    human_turn=human_turn_no,
                    phase="endorse",
                    consented=consented,
                    pending={str(a) for a in pending},
                )
                record_debate_convergence(run_meta, convergence_result)

            _, endorse_exit_reason = policy.should_exit_round(
                consensus_status=None,
                endorse_count=len(consented),
                active_agents=[str(a) for a in active],
                calls=calls,
                max_calls=cap_calls,
                rounds=parallel_round,
                max_rounds=cap_rounds,
                convergence_result=convergence_result,
                run_meta=run_meta,
                human_turn=human_turn_no,
            )
            if endorse_exit_reason in {"endorse_threshold", "convergence_threshold"} and pending:
                pending.clear()

            if not pending:
                from agent_lab.room.tasks import (
                    consensus_tasks_ready,
                    harvest_task_endorsements,
                )

                thread_all = list(messages) + list(all_replies)
                tasks_ready = True
                task_blockers: list[str] = []
                if run_meta is not None:
                    harvest_task_endorsements(
                        run_meta,
                        thread_all,
                        [str(a) for a in active],
                    )
                    tasks_ready, task_blockers = consensus_tasks_ready(run_meta, [str(a) for a in active])
                from agent_lab.room.objections import (
                    consensus_open_objection_blockers,
                    open_objections,
                    resolve_objections_on_endorse,
                )

                # 도전자의 수정안이 앵커가 되어 전원 동의 = 충돌이 결과를 바꿈.
                if run_meta is not None:
                    resolve_objections_on_endorse(
                        run_meta,
                        str(anchor.agent),
                        human_turn=_human_turn_number(human_turn_index),
                        resolution="challenger_authored_anchor",
                    )
                open_objs = open_objections(run_meta)
                max_r = max((m.parallel_round or 1) for m in all_replies)
                if open_objs:
                    obj_refs = consensus_open_objection_blockers(run_meta)
                    meta = {
                        "status": "incomplete",
                        "reason": "open_objections",
                        "anchor": anchor.to_dict(),
                        "rounds": max_r,
                        "agents_consented": consented,
                        "calls": calls,
                        "open_objections": obj_refs[:12],
                        "quality": quality,
                        **({"recombination": recomb_meta} if recomb_meta else {}),
                        "anchor_lineage": anchor_lineage,
                    }
                    sync_run_meta_turn_state(
                        run_meta,
                        thread_all,
                        active_agents=active,
                        consensus=meta,
                        plan_md=plan_md,
                    )
                    if on_event:
                        on_event(
                            "consensus_incomplete",
                            {
                                "reason": "open_objections",
                                "message": (
                                    "미해결 BLOCK/CHALLENGE가 있습니다. 작업 바에서 이의를 해소한 뒤 합의를 이어가세요."
                                ),
                                "open_objections": obj_refs[:8],
                            },
                        )
                    return all_replies, meta
                # 자동 ENDORSE 라운드 — 앵커는 합의됐지만 일부 작업에 팀 ENDORSE가
                # 부족할 때, Human이 "동의해 주세요"를 직접 칠 필요 없이 미동의
                # 에이전트에게 1회 재요청한다. cap_rounds/cap_calls가 상위 가드.
                if not tasks_ready and task_blockers and parallel_round < cap_rounds and calls < cap_calls:
                    from agent_lab.room.tasks import agents_missing_task_endorse
                    from agent_lab.room.consensus import (
                        consensus_task_endorse_follow_up,
                    )

                    need = [
                        a
                        for a in active
                        if str(a).strip().lower()
                        in set(agents_missing_task_endorse(run_meta, [str(x) for x in active]))
                    ]
                    if need:
                        parallel_round += 1
                        if on_event:
                            on_event(
                                "agent_round_start",
                                {
                                    "round": parallel_round,
                                    "total": cap_rounds,
                                    "consensus": True,
                                },
                            )
                        endorse_follow = consensus_task_endorse_follow_up(task_blockers)
                        endorse_thread = list(messages) + list(all_replies)
                        for aid in need:
                            if calls >= cap_calls:
                                break
                            check_cancelled()
                            msg = _invoke_agent_for_round(
                                aid,
                                topic=topic,
                                thread=endorse_thread,
                                parallel_round=parallel_round,
                                permissions=permissions,
                                review_mode=False,
                                review_advocate=None,
                                plan_md=plan_md,
                                run_meta=run_meta,
                                on_event=on_event,
                                context_log=context_log,
                                extra_follow_up=endorse_follow,
                                efficiency_mode=efficiency_mode,
                                slim_context=efficiency_mode,
                                human_turn_index=human_turn_index,
                            )
                            all_replies.append(msg)
                            endorse_thread.append(msg)
                            calls += 1
                        thread_all = list(messages) + list(all_replies)
                        tasks_ready = True
                        task_blockers = []
                        if run_meta is not None:
                            harvest_task_endorsements(
                                run_meta,
                                thread_all,
                                [str(a) for a in active],
                            )
                            tasks_ready, task_blockers = consensus_tasks_ready(
                                run_meta, [str(a) for a in active]
                            )
                        max_r = max((m.parallel_round or 1) for m in all_replies)

                if not tasks_ready:
                    meta = {
                        "status": "incomplete",
                        "reason": "open_tasks",
                        "anchor": anchor.to_dict(),
                        "rounds": max_r,
                        "agents_consented": consented,
                        "calls": calls,
                        "open_tasks": task_blockers[:12],
                        "quality": quality,
                        **({"recombination": recomb_meta} if recomb_meta else {}),
                        "anchor_lineage": anchor_lineage,
                    }
                    sync_run_meta_turn_state(
                        run_meta,
                        thread_all,
                        active_agents=active,
                        consensus=meta,
                        plan_md=plan_md,
                    )
                    if on_event:
                        on_event(
                            "consensus_incomplete",
                            {
                                "reason": "open_tasks",
                                "message": (
                                    "앵커 합의는 됐지만 열린 작업에 팀 ENDORSE가 부족합니다. "
                                    "envelope refs에 task id/제목을 넣거나 작업을 완료하세요."
                                ),
                                "open_tasks": task_blockers[:8],
                            },
                        )
                    return all_replies, meta
                meta = {
                    "status": "reached",
                    "anchor": anchor.to_dict(),
                    "rounds": max_r,
                    "agents_consented": consented,
                    "calls": calls,
                    "quality": quality,
                    **({"recombination": recomb_meta} if recomb_meta else {}),
                    "anchor_lineage": anchor_lineage,
                }
                sync_run_meta_turn_state(
                    run_meta,
                    thread_all,
                    active_agents=active,
                    consensus=meta,
                    plan_md=plan_md,
                )
                if on_event:
                    on_event("consensus_reached", meta)
                return all_replies, meta
            parallel_round += 1

        max_r = max((m.parallel_round or 1) for m in all_replies) if all_replies else 1
        meta = {
            "status": "incomplete",
            "anchor": anchor.to_dict(),
            "pending_agents": sorted(pending),
            "rounds": max_r,
            "agents_consented": consented,
            "calls": calls,
            "reason": "cap",
            "quality": quality,
            **({"recombination": recomb_meta} if recomb_meta else {}),
            "anchor_lineage": anchor_lineage,
        }
        sync_run_meta_turn_state(
            run_meta,
            list(messages) + list(all_replies),
            active_agents=active,
            consensus=meta,
            plan_md=plan_md,
            pending_agents=sorted(pending),
        )
        if on_event:
            on_event(
                "consensus_incomplete",
                {
                    **meta,
                    "message": (
                        f"합의 상한 도달 (라운드 {cap_rounds}, 호출 {cap_calls}). "
                        f"미응답: {', '.join(agent_label(a) for a in pending)}"
                    ),
                },
            )
        return all_replies, meta
    except RoomRunCancelled:
        return all_replies, None
