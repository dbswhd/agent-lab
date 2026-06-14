"""Session file I/O and turn harvest persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_lab.agents.registry import AGENT_IDS, AgentId, label
from agent_lab.consensus_agreements import (
    mark_agreements_plan_synced,
    record_consensus_agreement,
)
from agent_lab.session_guidance import (
    preserve_session_meta_from_prev,
)
from agent_lab.session import SESSIONS_DIR, session_dir
from agent_lab.room_messages import (
    ChatMessage,
    PLAN_FORMAT_VERSION,
    RUN_SCHEMA_VERSION,
    _current_turn_messages,
    _human_turn_count,
    _now,
)

def load_session_messages(folder: Path) -> list[ChatMessage]:
    from agent_lab.room_chat_channels import message_visibility

    chat_path = folder / "chat.jsonl"
    if not chat_path.is_file():
        return []
    messages: list[ChatMessage] = []
    for line in chat_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        pr = data.get("parallel_round")
        role = data.get("role", "system")
        content = data.get("content", "")
        messages.append(
            ChatMessage(
                role=role,
                agent=data.get("agent"),
                content=content,
                ts=data.get("ts", _now()),
                parallel_round=int(pr) if pr is not None else None,
                envelope=data.get("envelope"),
                visibility=message_visibility(
                    role=role,
                    content=content,
                    explicit=data.get("visibility"),
                ),
            )
        )
    return messages


def _append_peer_turn_digest(messages: list[ChatMessage]) -> list[ChatMessage]:
    """One peer-channel snapshot per human turn when R2+ agent replies exist."""
    from agent_lab.room_chat_channels import is_peer_visibility

    turn = _current_turn_messages(messages)
    for m in reversed(turn):
        if m.role == "system" and is_peer_visibility(m.visibility) and "peer digest" in (m.content or "").lower():
            return messages
    agent_lines: list[str] = []
    max_pr = 1
    for m in turn:
        if m.role != "agent":
            continue
        pr = m.parallel_round or 1
        max_pr = max(max_pr, pr)
        if pr < 2:
            continue
        if is_peer_visibility(m.visibility):
            continue
        agent = m.agent or "agent"
        body = (m.content or "").strip()
        if not body:
            continue
        from agent_lab.agents.registry import label

        agent_lines.append(f"**{label(agent)}** (R{pr}):\n{body[:4000]}\n")
    if not agent_lines:
        return messages
    digest = "[peer digest — internal coordination snapshot]\n\n" + "\n---\n".join(agent_lines)
    return messages + [
        ChatMessage(
            role="system",
            agent=None,
            content=digest,
            visibility="peer",
            parallel_round=max_pr,
        )
    ]


def _append_human_turn_synthesis(
    messages: list[ChatMessage],
    run_meta: dict[str, Any] | None,
    *,
    turn_meta: dict[str, Any] | None = None,
) -> list[ChatMessage]:
    """Human-channel turn summary (Sprint C) — one per completed human turn."""
    from agent_lab.room_team_orchestration import (
        build_human_turn_synthesis,
        is_human_synthesis_message,
        should_emit_human_turn_synthesis,
    )
    from agent_lab.room_tasks import team_lead

    if turn_meta and turn_meta.get("synthesize_only"):
        return messages
    if not messages:
        return messages
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return messages
    for m in messages[last_user + 1 :]:
        if is_human_synthesis_message(m.content, m.visibility):
            return messages
    turn_slice = messages[last_user:]
    turn_profile: str | None = None
    agents_used: list[str] | None = None
    if turn_meta:
        turn_profile = turn_meta.get("turn_profile")
        raw_agents = turn_meta.get("agents")
        if isinstance(raw_agents, list):
            agents_used = [str(a) for a in raw_agents]
    if run_meta:
        if not turn_profile:
            turn_profile = run_meta.get("turn_profile")
        if not turn_profile:
            turns = run_meta.get("turns") or []
            if turns and isinstance(turns[-1], dict):
                turn_profile = turns[-1].get("turn_profile")
        if agents_used is None:
            turns = run_meta.get("turns") or []
            if turns and isinstance(turns[-1], dict):
                raw_agents = turns[-1].get("agents")
                if isinstance(raw_agents, list):
                    agents_used = [str(a) for a in raw_agents]
    if not should_emit_human_turn_synthesis(turn_profile, turn_slice, agents_used=agents_used):
        return messages
    human_excerpt = messages[last_user].content or ""
    lead = team_lead(run_meta)
    body = build_human_turn_synthesis(
        turn_slice,
        lead=lead,
        human_excerpt=human_excerpt,
    )
    max_pr = max(
        (m.parallel_round or 1 for m in turn_slice if m.role == "agent"),
        default=1,
    )
    return messages + [
        ChatMessage(
            role="system",
            agent=None,
            content=body,
            visibility="human",
            parallel_round=max_pr,
        )
    ]


def _read_run_meta(folder: Path) -> dict[str, Any]:
    from agent_lab.run_meta import read_run_meta

    return read_run_meta(folder)


def _resolve_discuss_objections_from_consensus(
    run_meta: dict[str, Any],
    *,
    consensus: dict[str, Any] | None,
    human_turn: int,
) -> None:
    """합의 결과 replay — 도전자가 anchor를 endorse했거나 본인 수정안이 anchor가
    되어 전원 동의했으면 그 discuss CHALLENGE는 resolved_accepted다 (P3)."""
    if not isinstance(consensus, dict):
        return
    from agent_lab.room_objections import resolve_objections_on_endorse

    for agent in consensus.get("agents_consented") or []:
        resolve_objections_on_endorse(run_meta, str(agent), human_turn=human_turn)
    anchor = consensus.get("anchor")
    if consensus.get("status") == "reached" and isinstance(anchor, dict):
        resolve_objections_on_endorse(
            run_meta,
            str(anchor.get("agent") or ""),
            human_turn=human_turn,
            resolution="challenger_authored_anchor",
        )


def _sse_inbox_pending(folder: Path) -> bool:
    from agent_lab.human_inbox import compute_inbox_pending

    return compute_inbox_pending(_read_run_meta(folder))


def _session_context(folder: Path | None) -> tuple[str, dict[str, Any]]:
    """plan.md + run.json for trimmed agent payloads."""
    if not folder or not folder.is_dir():
        return "", {}
    plan_md = ""
    plan_path = folder / "plan.md"
    if plan_path.is_file():
        plan_md = plan_path.read_text(encoding="utf-8")
    return plan_md, _read_run_meta(folder)


def _prepare_team_coordination_before_round(
    folder: Path | None,
    run_meta: dict[str, Any],
    active_agents: list[AgentId],
    *,
    mode: str = "discuss",
    synthesize: bool = False,
    consensus_mode: bool = False,
) -> list[dict[str, Any]]:
    """Round-robin assign claimable tasks; persist run.json when session exists."""
    from agent_lab.room_tasks import assign_tasks_to_agents, ensure_team_lead
    from agent_lab.room_team_orchestration import should_assign_tasks_on_turn
    from agent_lab.run_meta import write_run_meta

    ensure_team_lead(run_meta)
    assigned: list[dict[str, Any]] = []
    if should_assign_tasks_on_turn(mode=mode, synthesize=synthesize, consensus_mode=consensus_mode):
        assigned = assign_tasks_to_agents(run_meta, [str(a) for a in active_agents])
    if folder and folder.is_dir():
        write_run_meta(folder, run_meta)
    return assigned


def _plan_content_normalized(plan_md: str) -> str:
    return plan_md.rstrip("\n") + "\n"


def _write_plan_if_changed(folder: Path, plan_md: str) -> bool:
    """Write plan.md only when content changes. Returns True if file was updated."""
    plan_path = folder / "plan.md"
    new_content = _plan_content_normalized(plan_md)
    if plan_path.is_file():
        existing = plan_path.read_text(encoding="utf-8")
        if existing == new_content:
            return False
    plan_path.write_text(new_content, encoding="utf-8")
    return True


def _find_completed_synthesize(folder: Path, request_id: str) -> dict[str, Any] | None:
    if not request_id:
        return None
    prev_run = _read_run_meta(folder)
    lpu = prev_run.get("last_plan_update") or {}
    if lpu.get("request_id") == request_id and lpu.get("status") == "completed":
        return lpu
    for turn in reversed(prev_run.get("turns") or []):
        if turn.get("request_id") == request_id and turn.get("mode") == "plan" and turn.get("status") == "completed":
            return turn
    return None


def _write_session_files(
    folder: Path,
    topic: str,
    messages: list[ChatMessage],
    plan_md: str,
    *,
    agents_used: list[str] | None = None,
    merge_meta: dict[str, Any] | None = None,
    turn_meta: dict[str, Any] | None = None,
    run_meta_patch: dict[str, Any] | None = None,
    clarifier_questions: list[str] | None = None,
) -> None:
    (folder / "topic.txt").write_text(topic.strip() + "\n", encoding="utf-8")
    plan_changed = _write_plan_if_changed(folder, plan_md)

    from agent_lab.room_chat_channels import is_peer_visibility

    transcript_lines = [f"# Room transcript\n\n**Topic:** {topic}\n"]
    for m in messages:
        if is_peer_visibility(m.visibility):
            continue
        if m.role == "user":
            transcript_lines.append(f"## Human\n\n{m.content}")
        elif m.role == "agent" and m.agent:
            transcript_lines.append(f"## {label(m.agent)}\n\n{m.content}")
        else:
            transcript_lines.append(f"## System\n\n{m.content}")
    (folder / "transcript.md").write_text("\n\n".join(transcript_lines) + "\n", encoding="utf-8")

    prev_run = _read_run_meta(folder)
    messages_to_store = _append_peer_turn_digest(list(messages))
    messages_to_store = _append_human_turn_synthesis(messages_to_store, prev_run, turn_meta=turn_meta)
    chat_path = folder / "chat.jsonl"
    with chat_path.open("w", encoding="utf-8") as f:
        for m in messages_to_store:
            f.write(json.dumps(m.to_dict(), ensure_ascii=False) + "\n")

    created_at = (merge_meta or {}).get("created_at") or _now()
    round_nums = [m.parallel_round for m in messages if m.role == "agent" and m.parallel_round is not None]
    agent_parallel_rounds = max(round_nums) if round_nums else 1
    turns: list[dict[str, Any]] = list(prev_run.get("turns") or [])
    agreements: list[dict[str, Any]] = list(prev_run.get("consensus_agreements") or [])
    if turn_meta:
        turn_ts = str(turn_meta.get("completed_at") or turn_meta.get("ts") or _now())
        agreements = record_consensus_agreement(
            agreements,
            consensus=turn_meta.get("consensus"),
            message_count=len(messages_to_store),
            ts=turn_ts,
        )
    if turn_meta:
        turns.append({**turn_meta, "ts": turn_meta.get("ts") or _now()})
    run_meta: dict[str, Any] = {
        "workflow_id": "room.parallel",
        "run_schema_version": RUN_SCHEMA_VERSION,
        "plan_format_version": PLAN_FORMAT_VERSION,
        "topic": topic,
        "created_at": created_at,
        "agents": agents_used or [a for a in AGENT_IDS],
        "status": turn_meta.get("status", "completed") if turn_meta else "completed",
        "message_count": len(messages_to_store),
        "agent_parallel_rounds": agent_parallel_rounds,
        "turns": turns,
        "actions": list(prev_run.get("actions") or []),
        "approvals": list(prev_run.get("approvals") or []),
        "executions": list(prev_run.get("executions") or []),
        "consensus_agreements": agreements,
    }
    preserve_session_meta_from_prev(run_meta, prev_run)
    if prev_run.get("human_inbox"):
        from agent_lab.human_inbox import compute_inbox_pending

        run_meta["human_inbox"] = list(prev_run["human_inbox"])
        run_meta["inbox_pending"] = compute_inbox_pending(run_meta)
    if run_meta_patch:
        run_meta.update(run_meta_patch)
    if turn_meta:
        if turn_meta.get("turn_lead"):
            run_meta["team_lead"] = turn_meta["turn_lead"]
        if turn_meta.get("turn_leads"):
            run_meta["turn_leads"] = turn_meta["turn_leads"]
    from agent_lab.session_guidance import sync_session_meta

    sync_session_meta(
        run_meta,
        topic=topic,
        messages=messages_to_store,
        plan_md=plan_md,
        permissions=(turn_meta or {}).get("permissions"),
    )
    from agent_lab.room_tasks import (
        auto_claim_tasks_from_turn,
        sync_tasks_after_turn,
        team_lead,
    )

    tm = turn_meta or {}
    sync_tasks_after_turn(
        run_meta,
        messages_to_store,
        human_turn=_human_turn_count(messages_to_store),
        plan_md=plan_md,
        mode=str(tm.get("mode") or "discuss"),
        synthesize=bool(tm.get("synthesize")),
        consensus_mode=bool(tm.get("consensus_mode")),
    )
    auto_claim_tasks_from_turn(
        run_meta,
        messages_to_store,
        lead_agent=team_lead(run_meta),
    )
    from agent_lab.room_mailbox import harvest_mailbox_from_turn

    harvest_mailbox_from_turn(
        run_meta,
        messages_to_store,
        human_turn=_human_turn_count(messages_to_store),
    )
    from agent_lab.room_dispatch_intents import harvest_dispatch_intents_from_turn

    harvest_dispatch_intents_from_turn(
        run_meta,
        messages_to_store,
        human_turn=_human_turn_count(messages_to_store),
        issuer_agent=team_lead(run_meta),
    )
    from agent_lab.room_objections import (
        apply_challenge_task_blocks,
        harvest_objections_from_turn,
    )

    harvest_objections_from_turn(
        run_meta,
        messages_to_store,
        human_turn=_human_turn_count(messages_to_store),
        mode=str(tm.get("mode") or "discuss"),
    )
    apply_challenge_task_blocks(run_meta)
    # P3: 턴 종료 dict는 디스크에서 다시 시작하므로, 합의 루프가 메모리에서
    # 해소한 discuss CHALLENGE를 consented/anchor 결과로 재적용한다.
    _resolve_discuss_objections_from_consensus(
        run_meta,
        consensus=tm.get("consensus") if isinstance(tm.get("consensus"), dict) else None,
        human_turn=_human_turn_count(messages_to_store),
    )
    from agent_lab.wisdom_index import harvest_agent_learnings

    harvest_agent_learnings(folder, messages_to_store)
    from agent_lab.inbox_harvest import (
        harvest_build_proposal,
        harvest_clarifier_questions,
        harvest_discuss_questions,
    )

    _inbox_human_turn = _human_turn_count(messages_to_store)
    _inbox_mode = str(tm.get("mode") or "discuss")
    if clarifier_questions:
        harvest_clarifier_questions(
            run_meta,
            clarifier_questions,
            human_turn=_inbox_human_turn,
        )
    harvest_discuss_questions(
        run_meta,
        messages_to_store,
        human_turn=_inbox_human_turn,
        plan_md=plan_md,
        mode=_inbox_mode,
        session_id=folder.name,
    )
    # Build proposal after questions so a pending question blocks build (§3.2).
    harvest_build_proposal(
        run_meta,
        plan_md=plan_md,
        human_turn=_inbox_human_turn,
        mode=_inbox_mode,
    )
    from agent_lab.room_artifacts import harvest_artifacts_from_turn

    harvest_artifacts_from_turn(
        run_meta,
        messages_to_store,
        human_turn=_human_turn_count(messages_to_store),
        session_folder=folder,
        turn_profile=str(tm.get("turn_profile") or run_meta.get("turn_profile") or ""),
        mode=str(tm.get("mode") or "discuss"),
    )
    from agent_lab.room_hooks import _hook_run_record, run_post_harvest_hooks
    from agent_lab.run_meta import append_hook_run

    harvest_hook = run_post_harvest_hooks(
        run_meta,
        session_folder=folder,
        session_id=str(run_meta.get("_session_id") or folder.name if folder else ""),
        human_turn=_human_turn_count(messages_to_store),
        mode=str(tm.get("mode") or "discuss"),
    )
    append_hook_run(
        folder,
        _hook_run_record(
            harvest_hook,
            session_id=str(run_meta.get("_session_id") or ""),
            human_turn=_human_turn_count(messages_to_store),
        ),
        run_meta=run_meta,
    )
    if plan_changed and plan_md.strip():
        from agent_lab.plan_provenance import extract_plan_provenance

        from agent_lab.room_tasks import RUN_PLAN_PROVENANCE_KEY

        run_meta[RUN_PLAN_PROVENANCE_KEY] = extract_plan_provenance(plan_md)
    if turn_meta:
        run_meta["last_turn"] = turns[-1]
        for key in (
            "mode",
            "synthesize",
            "permissions",
            "model",
            "latency_ms",
            "request_id",
            "started_at",
            "completed_at",
            "last_delegate",
            "dispatch_ledger",
        ):
            if key in turn_meta:
                run_meta[key] = turn_meta[key]
    if prev_run.get("last_plan_update"):
        run_meta["last_plan_update"] = prev_run["last_plan_update"]
    record_plan_update = bool(
        turn_meta
        and (plan_changed or turn_meta.get("plan_trigger") in ("consensus_reached", "verified_loop_done"))
        and (
            turn_meta.get("mode") == "plan"
            or turn_meta.get("plan_trigger")
            in (
                "auto_turn",
                "plan_turn",
                "consensus_reached",
                "verified_loop_done",
                "synthesize_only",
            )
        )
    )
    if record_plan_update:
        trigger = turn_meta.get("plan_trigger") or (
            "synthesize_only" if turn_meta.get("synthesize_only") else "plan_turn"
        )
        run_meta["last_plan_update"] = {
            "ts": turn_meta.get("completed_at") or turn_meta.get("ts") or _now(),
            "trigger": trigger,
            "mode": "plan",
            "synthesize_only": bool(turn_meta.get("synthesize_only") and trigger == "synthesize_only"),
            "request_id": turn_meta.get("request_id"),
            "started_at": turn_meta.get("started_at"),
            "completed_at": turn_meta.get("completed_at"),
            "agents": turn_meta.get("agents") or agents_used or [],
            "message_count": len(messages),
            "chat_from_line": 1,
            "chat_to_line": len(messages),
            "status": turn_meta.get("status", "completed"),
        }
        summary = turn_meta.get("plan_sync_summary")
        if isinstance(summary, str) and summary.strip():
            run_meta["last_plan_update"]["plan_sync_summary"] = summary.strip()
        if trigger == "consensus_reached":
            for row in reversed(agreements):
                if row.get("excerpt") and not row.get("plan_synced"):
                    run_meta["last_plan_update"]["consensus_excerpt"] = row["excerpt"]
                    break
        if trigger == "verified_loop_done":
            loop = run_meta.get("verified_loop") or {}
            loop_goal = loop.get("loop_goal") or {}
            goal_excerpt = str(loop_goal.get("text") or "").strip()
            if goal_excerpt:
                run_meta["last_plan_update"]["consensus_excerpt"] = goal_excerpt[:200]
        synced_at = str(turn_meta.get("completed_at") or turn_meta.get("ts") or _now())
        agreements = mark_agreements_plan_synced(
            agreements,
            message_count=len(messages),
            synced_at=synced_at,
        )
        run_meta["consensus_agreements"] = agreements
    from agent_lab.run_meta import write_run_meta

    write_run_meta(folder, run_meta)
    meta: dict[str, Any] = {
        "topic": topic,
        "created_at": created_at,
        "workflow": "room.parallel",
        "agents": run_meta["agents"],
    }
    if run_meta.get("session_phase"):
        meta["session_phase"] = run_meta["session_phase"]
    if run_meta.get("layout_frozen"):
        meta["layout_frozen"] = True
    if run_meta.get("workspace_preset"):
        meta["workspace_preset"] = run_meta["workspace_preset"]
    if run_meta.get("session_template"):
        meta["session_template"] = run_meta["session_template"]
    binding = run_meta.get("workspace_binding")
    if isinstance(binding, dict) and binding.get("label"):
        meta["workspace_label"] = binding["label"]
    if merge_meta:
        meta = {**merge_meta, **meta, "topic": topic, "agents": run_meta["agents"]}
    (folder / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def save_room_session(
    topic: str,
    messages: list[ChatMessage],
    plan_md: str,
    *,
    base: Path | None = None,
    agents_used: list[str] | None = None,
    turn_meta: dict[str, Any] | None = None,
    clarifier_questions: list[str] | None = None,
) -> Path:
    folder = session_dir(topic, base=base or SESSIONS_DIR)
    _write_session_files(
        folder,
        topic,
        messages,
        plan_md,
        agents_used=agents_used,
        turn_meta=turn_meta,
        clarifier_questions=clarifier_questions,
    )
    return folder

