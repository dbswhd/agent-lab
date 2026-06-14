"""Consensus-mode multi-round agent orchestration."""

from __future__ import annotations

from typing import Any

from agent_lab.agents.registry import AgentId, available_agents, label
from agent_lab.room_consensus import (
    consensus_follow_up,
    consensus_reply_verdict,
    debate_review_round,
    is_substantive_reply,
    pick_anchor,
    recombination_follow_up,
)
from agent_lab.room_turn_state import sync_run_meta_turn_state
from agent_lab.run_control import RoomRunCancelled, check_cancelled
from agent_lab.room_messages import (
    ChatMessage,
    MAX_AGENTS_PER_ROUND,
    OnAgentEvent,
    _agent_turn_failed,
    _current_turn_messages,
    _distinct_substantive_proposers,
    _human_turn_number,
    _is_agent_error_message,
    _is_valid_synthesis,
    _review_advocate,
)

from agent_lab.room_agent_invoke import (
    _invoke_agent_for_round,
)
from agent_lab.room_parallel_rounds import run_parallel_round


def run_consensus_agent_rounds(
    topic: str,
    messages: list[ChatMessage],
    *,
    agents: list[AgentId] | None = None,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    human_turn_index: int = 0,
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
    context_log: list[dict[str, Any]] | None = None,
    efficiency_mode: bool = False,
) -> tuple[list[ChatMessage], dict[str, Any] | None]:
    """자유 토론: R1 병렬 후 앵커 제안에 전원 「이의 없습니다」까지 순차 반복."""
    from agent_lab.topic_router import (
        batch_escalation_act,
        escalate_route,
        resolve_topic_route,
        route_debate_last,
    )

    active = list(agents or available_agents())[:MAX_AGENTS_PER_ROUND]
    if not active:
        raise RuntimeError("No agents available.")

    all_replies: list[ChatMessage] = []
    calls = 0
    route = resolve_topic_route(
        topic,
        turn_profile=str((run_meta or {}).get("turn_profile") or ""),
        session_template=str((run_meta or {}).get("session_template") or ""),
        efficiency_mode=efficiency_mode,
    )
    cap_rounds, cap_calls = route.max_rounds, route.max_calls
    if run_meta is not None:
        run_meta["_turn_category"] = route.category_dict()

    def _harvest_discuss_objections(thread: list[ChatMessage]) -> None:
        """충돌을 상태로 — discuss CHALLENGE/BLOCK을 run.json objections에 등록 (P3)."""
        if run_meta is None:
            return
        from agent_lab.room_objections import harvest_objections_from_turn

        harvest_objections_from_turn(
            run_meta,
            thread,
            human_turn=_human_turn_number(human_turn_index),
            mode="discuss",
        )

    def _maybe_escalate(batch_msgs: list[ChatMessage]) -> None:
        """충돌 act → 카테고리 1단계 상승 (예산만 늘림, 강등 없음)."""
        nonlocal route, cap_rounds, cap_calls
        act = batch_escalation_act(batch_msgs)
        if not act:
            return
        escalated = escalate_route(route, act=act, efficiency_mode=efficiency_mode)
        if escalated.category == route.category:
            return
        route = escalated
        cap_rounds, cap_calls = route.max_rounds, route.max_calls
        if run_meta is not None:
            run_meta["_turn_category"] = route.category_dict()
            from agent_lab.inbox_harvest import record_escalation_harvest_keys

            record_escalation_harvest_keys(run_meta, batch_msgs, act=act)
        if on_event:
            on_event(
                "category_escalated",
                {
                    "from": route.escalated_from,
                    "to": route.category,
                    "act": route.escalation_act,
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
                from agent_lab.inbox_harvest import harvest_and_check_pause

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
            for m in all_replies
            if isinstance(getattr(m, "envelope", None), dict)
            and str(m.envelope.get("act") or "").upper() in ("CHALLENGE", "BLOCK", "AMEND")
        )

        # P4 재조합 라운드 — debate 종료 → pick_anchor 사이의 명시적 합성(crossover).
        recomb_meta: dict[str, Any] | None = None
        recomb_rounds = 0
        if route.recombination != "off" and len(active) >= 2:
            skip_reason = ""
            if calls + len(active) > cap_calls:
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
        forced_review_rounds = 0
        if route.quality_gate and debate_conflicts == 0 and len(active) >= 2 and calls < cap_calls:
            check_cancelled()
            advocate = _review_advocate(active, human_turn_index)
            quality["forced_review"] = True
            quality["advocate"] = str(advocate)
            forced_review_rounds = 1
            if on_event:
                on_event(
                    "quality_gate_review",
                    {
                        "agent": advocate,
                        "category": route.category,
                        "round": last_debate + 1 + recomb_rounds,
                        "message": (
                            f"{label(advocate)}에게 합의 전 강제 반론 라운드를 요청합니다 "
                            f"(토론 무충돌 · {route.category})."
                        ),
                    },
                )
            review_msg = _invoke_agent_for_round(
                advocate,
                topic=topic,
                thread=working,
                parallel_round=last_debate + 1 + recomb_rounds,
                permissions=permissions,
                review_mode=False,
                review_advocate=None,
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
            from agent_lab.room_tasks import open_tasks_for_consensus

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
                        from agent_lab.room_objections import (
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

            if not pending:
                from agent_lab.room_tasks import (
                    consensus_tasks_ready,
                    harvest_task_endorsements,
                )

                thread_all = list(messages) + list(all_replies)
                harvest_task_endorsements(
                    run_meta,
                    thread_all,
                    [str(a) for a in active],
                )
                tasks_ready, task_blockers = consensus_tasks_ready(run_meta, [str(a) for a in active])
                from agent_lab.room_objections import (
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
                        f"미응답: {', '.join(label(a) for a in pending)}"
                    ),
                },
            )
        return all_replies, meta
    except RoomRunCancelled:
        return all_replies, None
