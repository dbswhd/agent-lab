"""Multi-agent room: Cursor + Codex + Claude in parallel (controlled workflow)."""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_lab.agents.prompts import room_scribe_prompt
from agent_lab.agents.registry import AGENT_IDS, AgentId, available_agents, call_agent, label, model_label
from agent_lab.attachments import describe_attachments
from agent_lab.context_bundle import build_context_bundle
from agent_lab.context_meta import summarize_turn_context
from agent_lab.agent_envelope import (
    is_endorse_reply,
    is_pass_reply,
    parse_agent_response_v2,
)
from agent_lab.room_consensus import (
    consensus_follow_up,
    consensus_reply_verdict,
    debate_review_round,
    is_substantive_reply,
    pick_anchor,
    recombination_follow_up,
)
from agent_lab.consensus_agreements import (
    mark_agreements_plan_synced,
    record_consensus_agreement,
)
from agent_lab.room_turn_state import sync_run_meta_turn_state
from agent_lab.session_guidance import (
    apply_discuss_workspace,
    preserve_session_meta_from_prev,
    resolve_session_workspace_binding,
)
from agent_lab.agent_permissions import apply_discuss_executor_policy
from agent_lab.cli_retry import is_retryable, retry_attempts, retryable_failure
from agent_lab.run_control import RoomRunCancelled, check_cancelled, is_cancelled
from agent_lab.session import SESSIONS_DIR, session_dir

MAX_AGENTS_PER_ROUND = 3
MAX_AGENT_PARALLEL_ROUNDS = 4  # per human message
DEFAULT_AGENT_PARALLEL_ROUNDS = 1  # discuss default; use 2+ for review / peer debate
RUN_SCHEMA_VERSION = 1
PLAN_FORMAT_VERSION = 1  # 지금 실행 + 실행 순서 sections
# Review round 2+: sequential pipeline (matches web ROOM_MODEL_AGENT_ORDER).
REVIEW_ROUND2_ORDER: tuple[AgentId, ...] = ("claude", "codex", "cursor")


@dataclass
class ChatMessage:
    role: str  # user | agent | system
    agent: str | None
    content: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parallel_round: int | None = None  # 1..N within one human turn
    envelope: dict[str, Any] | None = None
    visibility: str = "human"  # human | peer (peer = coordination channel)
    envelope_parse_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        from agent_lab.room_chat_channels import normalize_visibility

        d: dict[str, Any] = {
            "role": self.role,
            "agent": self.agent,
            "content": self.content,
            "ts": self.ts,
        }
        if self.parallel_round is not None:
            d["parallel_round"] = self.parallel_round
        if self.envelope:
            d["envelope"] = self.envelope
        if self.envelope_parse_error:
            d["envelope_parse_error"] = True
        vis = normalize_visibility(self.visibility)
        if vis != "human":
            d["visibility"] = vis
        return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_thread(topic: str, messages: list[ChatMessage]) -> str:
    lines = [f"Human topic:\n{topic.strip()}\n"]
    for m in messages:
        if m.role == "user":
            lines.append(f"Human:\n{m.content}\n")
        elif m.role == "agent" and m.agent:
            lines.append(f"{label(m.agent)}:\n{m.content}\n")
    return "\n".join(lines)


def _human_turn_count(messages: list[ChatMessage]) -> int:
    return sum(1 for m in messages if m.role == "user")


def _review_advocate(agents: list[AgentId], human_turn_index: int) -> AgentId:
    """Rotate devil's advocate by human turn (0-based index before current round)."""
    if not agents:
        raise ValueError("agents required for review mode")
    return agents[human_turn_index % len(agents)]


_LINE_REF_RE = re.compile(r"(?:chat\.jsonl#)?L(\d+)$", re.IGNORECASE)


def _ref_line_authors(
    refs: list[Any],
    thread: list[ChatMessage],
) -> set[str]:
    """envelope refs(`L{n}`/`chat.jsonl#L{n}`) → 발화 에이전트 집합 (1-based 라인)."""
    authors: set[str] = set()
    for ref in refs or []:
        m = _LINE_REF_RE.match(str(ref).strip())
        if not m:
            continue
        n = int(m.group(1))
        if 1 <= n <= len(thread):
            msg = thread[n - 1]
            if msg.role == "agent" and msg.agent:
                authors.add(str(msg.agent))
    return authors


def _distinct_substantive_proposers(replies: list[ChatMessage]) -> int:
    """debate에서 실질 제안 act를 낸 서로 다른 에이전트 수 (재조합 auto-skip 판정)."""
    agents: set[str] = set()
    for m in replies:
        env = getattr(m, "envelope", None)
        if not isinstance(env, dict):
            continue
        if str(env.get("act") or "").upper() in ("PROPOSE", "AMEND", "CHALLENGE", "BLOCK"):
            if m.agent:
                agents.add(str(m.agent))
    return len(agents)


def _is_valid_synthesis(msg: ChatMessage, thread: list[ChatMessage]) -> bool:
    """재조합 검증(v1 텔레메트리): PROPOSE/AMEND + refs가 다른 에이전트 2명 이상."""
    env = getattr(msg, "envelope", None)
    if not isinstance(env, dict):
        return False
    if str(env.get("act") or "").upper() not in ("PROPOSE", "AMEND"):
        return False
    authors = _ref_line_authors(list(env.get("refs") or []), thread)
    authors.discard(str(msg.agent or ""))
    return len(authors) >= 2


def _current_turn_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Agent replies after the latest human message (same human turn)."""
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return messages
    return messages[last_user + 1 :]


def _round_agent_order(
    agents: list[AgentId],
    *,
    review_mode: bool,
    parallel_round: int,
    run_meta: dict[str, Any] | None = None,
) -> list[AgentId]:
    if run_meta:
        from agent_lab.room_team_orchestration import normalize_turn_profile

        if normalize_turn_profile(run_meta.get("turn_profile")) == "specialist":
            from agent_lab.room_agent_capabilities import specialist_round_agents

            ordered = specialist_round_agents([str(a) for a in agents], parallel_round)
            pool = {str(a).lower(): a for a in agents}
            return [pool[k] for k in ordered if k in pool]
    if review_mode and parallel_round >= 2:
        return [a for a in REVIEW_ROUND2_ORDER if a in agents]
    if parallel_round == 1 and run_meta and not review_mode:
        from agent_lab.room_team_orchestration import team_r1_split

        teammates, lead_tail = team_r1_split([str(a) for a in agents], run_meta)
        if lead_tail and teammates:
            order = teammates + lead_tail
            pool = {str(a).lower(): a for a in agents}
            return [pool[k] for k in order if k in pool]
    return agents


def _agent_user_payload(
    topic: str,
    messages: list[ChatMessage],
    agent: AgentId,
    *,
    permissions: dict | None = None,
    parallel_round: int = 1,
    review_mode: bool = False,
    review_advocate: AgentId | None = None,
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
) -> str:
    from agent_lab.agent_permissions import permission_preamble

    bundle = build_context_bundle(
        topic,
        messages,
        agent,
        permission_lines=permission_preamble(permissions, agent, run_meta),
        parallel_round=parallel_round,
        review_mode=review_mode,
        review_advocate=review_advocate,
        plan_md=plan_md,
        run_meta=run_meta,
        permissions=permissions,
        all_messages=messages,
    )
    return bundle.render()


def build_agent_context_bundle(
    topic: str,
    messages: list[ChatMessage],
    agent: AgentId,
    *,
    permissions: dict | None = None,
    parallel_round: int = 1,
    review_mode: bool = False,
    review_advocate: AgentId | None = None,
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
    efficiency_mode: bool = False,
    slim_context: bool = False,
    consensus_mode: bool = False,
):
    """ContextBundle for preview / debugging (payload + layer metadata)."""
    from agent_lab.agent_permissions import permission_preamble

    return build_context_bundle(
        topic,
        messages,
        agent,
        permission_lines=permission_preamble(permissions, agent, run_meta),
        parallel_round=parallel_round,
        review_mode=review_mode,
        review_advocate=review_advocate,
        plan_md=plan_md,
        run_meta=run_meta,
        permissions=permissions,
        all_messages=messages,
        efficiency_mode=efficiency_mode,
        slim_context=slim_context,
        consensus_mode=consensus_mode,
    )


OnAgentEvent = Callable[[str, dict[str, Any]], None]
# event types: agent_start, agent_activity, agent_done, agent_error, turn_failed


def _effective_discuss_permissions(
    permissions: dict | None,
    *,
    topic: str,
    plan_md: str,
    run_meta: dict[str, Any] | None,
) -> dict:
    binding = resolve_session_workspace_binding(
        permissions,
        topic=topic,
        plan_md=plan_md,
        run_meta=run_meta,
    )
    perms = apply_discuss_executor_policy(permissions, discuss=True)
    return apply_discuss_workspace(perms, binding)


def _agent_turn_failed(replies: list[ChatMessage]) -> bool:
    return any(m.role == "system" and m.agent for m in replies)


def _is_agent_error_message(msg: ChatMessage) -> bool:
    return msg.role == "system" and bool(msg.agent)


def _agent_turn_summary(replies: list[ChatMessage]) -> dict[str, list[str]]:
    failed = sorted({str(m.agent) for m in replies if m.role == "system" and m.agent})
    succeeded = sorted({str(m.agent) for m in replies if m.role == "agent" and m.agent})
    return {"failed_agents": failed, "succeeded_agents": succeeded}


def _turn_status_from_replies(
    replies: list[ChatMessage],
    *,
    cancelled: bool,
    consensus_meta: dict[str, Any] | None = None,
    consensus_mode: bool = False,
) -> str:
    if cancelled:
        return "cancelled"
    summary = _agent_turn_summary(replies)
    failed = summary["failed_agents"]
    succeeded = summary["succeeded_agents"]
    if consensus_meta is not None and consensus_meta.get("status") == "failed":
        return "failed"
    if consensus_mode and failed:
        return "failed"
    if failed and succeeded:
        return "partial"
    if failed:
        return "failed"
    return "completed"


def _emit_turn_terminal_status(
    *,
    status: str,
    replies: list[ChatMessage],
    on_event: OnAgentEvent | None,
    consensus_mode: bool,
) -> None:
    if not on_event or status not in {"partial", "failed"}:
        return
    summary = _agent_turn_summary(replies)
    payload = {
        "status": status,
        **summary,
        "reason": "agent_error",
        "consensus": consensus_mode,
    }
    if status == "partial":
        on_event("turn_partial", payload)
    else:
        on_event("turn_failed", payload)


def _human_turn_number(human_turn_index: int) -> int:
    return max(1, human_turn_index + 1)


def _session_folder_from_run_meta(run_meta: dict[str, Any] | None) -> Path | None:
    if not run_meta:
        return None
    folder_raw = run_meta.get("_session_folder")
    if not folder_raw:
        return None
    folder = Path(str(folder_raw))
    return folder if folder.is_dir() else None


def _try_replay_completed_agent(
    aid: AgentId,
    *,
    human_turn_index: int,
    parallel_round: int,
    run_meta: dict[str, Any] | None,
    on_event: OnAgentEvent | None,
) -> ChatMessage | None:
    folder = _session_folder_from_run_meta(run_meta)
    if not folder:
        return None
    from agent_lab.run_meta import get_completed_step, read_run_meta

    human_turn = _human_turn_number(human_turn_index)
    run = run_meta or read_run_meta(folder)
    step = get_completed_step(
        run,
        human_turn=human_turn,
        parallel_round=parallel_round,
        agent=str(aid),
    )
    if not step:
        return None
    content = str(step.get("content") or "")
    envelope = step.get("envelope")
    if on_event:
        from agent_lab.room_sse_stream import emit_agent_tokens

        on_event(
            "agent_start",
            {"agent": aid, "round": parallel_round, "resumed": True},
        )
        emit_agent_tokens(
            on_event,
            agent=str(aid),
            round=parallel_round,
            text=content,
        )
        on_event(
            "agent_done",
            {
                "agent": aid,
                "round": parallel_round,
                "chars": len(content),
                "content": content,
                "pass": is_pass_reply(content, envelope if isinstance(envelope, dict) else None),
                "no_objection": is_endorse_reply(content, envelope if isinstance(envelope, dict) else None),
                "envelope": envelope,
                "envelope_valid": isinstance(envelope, dict),
                "resumed": True,
                "skipped_call": True,
                "completed_step": step.get("step"),
            },
        )
    from agent_lab.room_chat_channels import message_visibility

    return ChatMessage(
        role="agent",
        agent=aid,
        content=content,
        parallel_round=parallel_round,
        envelope=envelope if isinstance(envelope, dict) else None,
        visibility=message_visibility(role="agent", content=content),
    )


def _invoke_agent_for_round(
    aid: AgentId,
    *,
    topic: str,
    thread: list[ChatMessage],
    parallel_round: int,
    permissions: dict | None,
    review_mode: bool,
    review_advocate: AgentId | None,
    plan_md: str,
    run_meta: dict[str, Any] | None,
    on_event: OnAgentEvent | None,
    context_log: list[dict[str, Any]] | None = None,
    extra_follow_up: str = "",
    efficiency_mode: bool = False,
    slim_context: bool = False,
    human_turn_index: int = 0,
) -> ChatMessage:
    replay = _try_replay_completed_agent(
        aid,
        human_turn_index=human_turn_index,
        parallel_round=parallel_round,
        run_meta=run_meta,
        on_event=on_event,
    )
    if replay is not None:
        return replay
    return _call_one_agent(
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
        extra_follow_up=extra_follow_up,
        efficiency_mode=efficiency_mode,
        slim_context=slim_context,
        human_turn_index=human_turn_index,
    )


def _finalize_durable_turn(folder: Path, human_turn_num: int, turn_status: str) -> None:
    if turn_status != "completed":
        return
    from agent_lab.run_meta import clear_completed_steps_for_human_turn

    clear_completed_steps_for_human_turn(folder, human_turn_num)


def _bind_session_to_run_meta(
    run_meta: dict[str, Any] | None,
    folder: Path | None,
) -> None:
    if not run_meta or not folder or not folder.is_dir():
        return
    run_meta["_session_folder"] = str(folder.resolve())
    run_meta["_session_id"] = folder.name
    from agent_lab.agent_hooks_materializer import ensure_session_agent_hooks_from_config

    manifest = ensure_session_agent_hooks_from_config(folder)
    if manifest:
        run_meta["agent_hooks_manifest"] = manifest


def _set_active_turn_flags(
    run_meta: dict[str, Any] | None,
    *,
    mode: str,
    synthesize: bool,
    consensus_mode: bool,
) -> None:
    if not run_meta:
        return
    run_meta["_active_turn_mode"] = mode
    run_meta["_active_synthesize"] = synthesize
    run_meta["_active_consensus"] = consensus_mode


def _teammate_idle_peer_message(
    aid: AgentId,
    run_meta: dict[str, Any] | None,
    *,
    parallel_round: int,
) -> ChatMessage | None:
    if not run_meta:
        return None
    from agent_lab.room_hooks import run_teammate_idle_hooks
    from agent_lab.room_tasks import list_tasks

    agent_l = str(aid).strip().lower()
    in_prog = [t for t in list_tasks(run_meta) if t.get("owner_agent") == agent_l and t.get("status") == "in_progress"]
    folder_raw = run_meta.get("_session_folder")
    folder = Path(str(folder_raw)) if folder_raw else None
    nudge = run_teammate_idle_hooks(
        run_meta,
        agent_l,
        session_folder=folder,
        session_id=str(run_meta.get("_session_id") or ""),
        in_progress_tasks=in_prog,
    )
    if not nudge:
        return None
    return ChatMessage(
        role="system",
        agent=None,
        content=f"[idle gate · {agent_l}]\n{nudge}",
        visibility="peer",
        parallel_round=parallel_round,
    )


def _call_one_agent(
    aid: AgentId,
    *,
    topic: str,
    thread: list[ChatMessage],
    parallel_round: int,
    permissions: dict | None,
    review_mode: bool,
    review_advocate: AgentId | None,
    plan_md: str,
    run_meta: dict[str, Any] | None,
    on_event: OnAgentEvent | None,
    context_log: list[dict[str, Any]] | None = None,
    extra_follow_up: str = "",
    efficiency_mode: bool = False,
    slim_context: bool = False,
    human_turn_index: int = 0,
) -> ChatMessage:
    def _emit(typ: str, payload: dict[str, Any]) -> None:
        if on_event:
            on_event(typ, payload)

    _emit("agent_start", {"agent": aid, "round": parallel_round})

    def _activity(line: str) -> None:
        from agent_lab.room_sse_stream import maybe_emit_tool_events

        _emit(
            "agent_activity",
            {"agent": aid, "round": parallel_round, "text": line},
        )
        maybe_emit_tool_events(
            _emit,
            agent=str(aid),
            round=parallel_round,
            line=line,
        )

    streamed_live = False

    def _bridge_event(kind: str, data: dict[str, Any]) -> None:
        nonlocal streamed_live
        if kind == "text":
            chunk = str(data.get("text") or "")
            if not chunk:
                return
            streamed_live = True
            _emit(
                "agent_token",
                {"agent": aid, "round": parallel_round, "text": chunk},
            )
            return
        if kind == "tool_start":
            _emit(
                "tool_start",
                {
                    "agent": aid,
                    "round": parallel_round,
                    "tool": data.get("tool", "tool"),
                    "args": data.get("args") or {},
                },
            )
            return
        if kind == "tool_output":
            _emit(
                "tool_output",
                {
                    "agent": aid,
                    "round": parallel_round,
                    "tool": data.get("tool", "tool"),
                    "chunk": data.get("chunk", ""),
                },
            )
            return
        if kind == "tool_done":
            _emit(
                "tool_done",
                {
                    "agent": aid,
                    "round": parallel_round,
                    "tool": data.get("tool", "tool"),
                },
            )
            return
        if kind == "activity":
            line = str(data.get("text") or "")
            if line:
                _activity(line)

    if aid == "cursor":
        _activity("Cursor bridge 연결 중…")

    effective_permissions = _effective_discuss_permissions(
        permissions,
        topic=topic,
        plan_md=plan_md,
        run_meta=run_meta,
    )

    from agent_lab.room_team_orchestration import is_discuss_only_turn, lead_discuss_role_block

    consensus_mode = bool(run_meta and run_meta.get("_active_consensus"))
    review_mode_active = review_mode
    turn_profile = str((run_meta or {}).get("turn_profile") or "").strip()
    folder = _session_folder_from_run_meta(run_meta)
    session_id = str((run_meta or {}).get("_session_id") or "")
    human_turn = _human_turn_number(human_turn_index)

    from agent_lab.runtime.policy import PolicyEngine
    from agent_lab.room_hooks import (
        _hook_run_record,
        run_post_agent_reply_hooks,
        run_pre_agent_reply_hooks,
    )
    from agent_lab.run_meta import append_hook_run

    gate_snap = PolicyEngine.gate_snapshot(run_meta)
    from agent_lab.reply_policy import resolve_reply_policy
    from agent_lab.structured_envelope_adapter import should_request_structured_envelope

    reply_policy = resolve_reply_policy(
        parallel_round=parallel_round,
        review_mode=review_mode_active,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile,
        efficiency_mode=efficiency_mode,
    )
    request_structured = should_request_structured_envelope(reply_policy)

    def _emit_hook_event(hook_result: Any, event_name: str) -> None:
        if not (hook_result.feedback.strip() or hook_result.blocked):
            return
        feedback = hook_result.feedback[:500]
        _emit(
            "hook_event",
            {
                "agent": aid,
                "event": event_name,
                "round": parallel_round,
                "blocked": hook_result.blocked,
                "feedback": feedback,
                "sub_reason": hook_result.sub_reason,
                "retryable": getattr(hook_result, "retryable", False),
            },
        )
        tag = "blocked" if hook_result.blocked else "warn"
        detail = (feedback or hook_result.sub_reason or event_name).strip()[:120]
        _activity(f"[hook · {event_name} · {tag}] {detail}")

    pre_hook = run_pre_agent_reply_hooks(
        run_meta or {},
        str(aid),
        session_folder=folder,
        session_id=session_id,
        parallel_round=parallel_round,
        consensus_mode=consensus_mode,
        review_mode=review_mode_active,
        turn_profile=turn_profile,
        gate_snapshot=gate_snap,
        human_turn=human_turn,
    )
    _emit_hook_event(pre_hook, "pre_agent_reply")
    append_hook_run(
        folder,
        _hook_run_record(
            pre_hook,
            agent=str(aid),
            session_id=session_id,
            human_turn=human_turn,
            parallel_round=parallel_round,
        ),
        run_meta=run_meta,
    )

    lead_block = ""
    if run_meta and is_discuss_only_turn(
        mode=str(run_meta.get("_active_turn_mode") or "discuss"),
        synthesize=bool(run_meta.get("_active_synthesize")),
        consensus_mode=consensus_mode,
    ):
        lead_block = lead_discuss_role_block(aid, run_meta)
    hook_prepend = pre_hook.feedback.strip()
    from agent_lab.plan_workflow import PLAN_CLARIFY_GUIDANCE, plan_workflow_wants_inbox_mcp

    plan_clarify = ""
    if run_meta and plan_workflow_wants_inbox_mcp(run_meta):
        plan_clarify = PLAN_CLARIFY_GUIDANCE
    combined_follow = "\n\n".join(
        x for x in (lead_block, hook_prepend, plan_clarify, extra_follow_up) if x and x.strip()
    )

    def _invoke_agent(payload: str):
        from agent_lab.agents.registry import call_agent_reply
        from agent_lab.cursor_inbox_mcp import discuss_inbox_mcp_enabled

        use_inbox_mcp = discuss_inbox_mcp_enabled(run_meta)
        agent_reply = call_agent_reply(
            aid,
            "",
            payload,
            permissions=effective_permissions,
            on_activity=_activity if aid in ("cursor", "codex", "claude") else None,
            on_bridge_event=_bridge_event if aid in ("cursor", "codex", "claude") else None,
            session_folder=folder,
            request_structured_envelope=request_structured,
            inbox_mcp=use_inbox_mcp,
        )
        text = agent_reply.text
        parsed = parse_agent_response_v2(
            text,
            structured=agent_reply.structured_envelope,
        )
        envelope_dict = parsed.envelope.to_dict() if parsed.envelope else None
        body = parsed.body or text
        post_hook = run_post_agent_reply_hooks(
            run_meta or {},
            str(aid),
            content=body,
            envelope=envelope_dict,
            envelope_parse_error=parsed.envelope_parse_error,
            session_folder=folder,
            session_id=session_id,
            parallel_round=parallel_round,
            consensus_mode=consensus_mode,
            review_mode=review_mode_active,
            turn_profile=turn_profile,
            gate_snapshot=gate_snap,
            human_turn=human_turn,
        )
        append_hook_run(
            folder,
            _hook_run_record(
                post_hook,
                agent=str(aid),
                session_id=session_id,
                human_turn=human_turn,
                parallel_round=parallel_round,
            ),
            run_meta=run_meta,
        )
        _emit_hook_event(post_hook, "post_agent_reply")
        return text, parsed, envelope_dict, body, post_hook

    try:
        bundle = build_agent_context_bundle(
            topic,
            thread,
            aid,
            permissions=permissions,
            parallel_round=parallel_round,
            review_mode=review_mode,
            review_advocate=review_advocate,
            plan_md=plan_md,
            run_meta=run_meta,
            efficiency_mode=efficiency_mode,
            slim_context=slim_context,
            consensus_mode=consensus_mode,
        )
        payload = bundle.render()
        if combined_follow.strip():
            payload = f"{payload}\n\n{combined_follow.strip()}"
        context_meta = bundle.meta.to_dict()
        context_meta["model"] = model_label(aid)
        if context_log is not None:
            context_log.append(context_meta)

        text, parsed, envelope_dict, body, post_hook = _invoke_agent(payload)
        needs_envelope_fix = reply_policy.envelope_strict and (parsed.envelope_parse_error or parsed.envelope is None)
        if consensus_mode and ((post_hook.blocked and post_hook.retryable) or needs_envelope_fix):
            if post_hook.blocked and post_hook.feedback.strip():
                retry_follow = f"[Hook — envelope/format fix required]\n{post_hook.feedback.strip()}"
            else:
                retry_follow = (
                    "[Envelope required — consensus R2+]\n"
                    "Reply must start with ```agent-envelope fenced JSON "
                    '({"act":"ENDORSE",...}) then your body.'
                )
            retry_payload = f"{payload}\n\n{retry_follow}"
            text, parsed, envelope_dict, body, post_hook = _invoke_agent(retry_payload)

        from agent_lab.room_chat_channels import message_visibility

        msg = ChatMessage(
            role="agent",
            agent=aid,
            content=body,
            parallel_round=parallel_round,
            envelope=envelope_dict,
            visibility=message_visibility(role="agent", content=body),
            envelope_parse_error=parsed.envelope_parse_error,
        )
        if parallel_round >= 2 and (consensus_mode or review_mode_active):
            if parsed.envelope_parse_error:
                _activity("[envelope · parse_error] R2+ fence/JSON invalid")
            elif not (envelope_dict or {}).get("act"):
                _activity("[envelope · missing] R2+ act required")
        from agent_lab.room_sse_stream import emit_agent_tokens

        if not streamed_live:
            emit_agent_tokens(
                _emit,
                agent=str(aid),
                round=parallel_round,
                text=body,
            )
        _emit(
            "agent_done",
            {
                "agent": aid,
                "chars": len(body),
                "content": body,
                "round": parallel_round,
                "pass": is_pass_reply(body, envelope_dict),
                "no_objection": is_endorse_reply(body, envelope_dict),
                "envelope": envelope_dict,
                "envelope_valid": parsed.envelope is not None,
                "envelope_parse_error": parsed.envelope_parse_error,
                "context_meta": context_meta,
                "hook_blocked": post_hook.blocked,
            },
        )
        if folder and msg.role == "agent":
            from agent_lab.run_meta import record_completed_step

            record_completed_step(
                folder,
                human_turn=human_turn,
                parallel_round=parallel_round,
                agent=str(aid),
                content=body,
                envelope=envelope_dict,
                run_meta=run_meta,
            )
            from agent_lab.mission_board import record_agent_call

            record_agent_call(
                folder,
                human_turn=human_turn,
                agent=str(aid),
                run_meta=run_meta,
            )
        return msg
    except Exception as e:
        retryable = retryable_failure(e) or is_retryable(str(e))
        attempts = retry_attempts(e)
        _emit(
            "agent_error",
            {
                "agent": aid,
                "message": str(e),
                "round": parallel_round,
                "failed": True,
                "retryable": retryable,
                "attempts": attempts,
            },
        )
        return ChatMessage(
            role="system",
            agent=aid,
            content=f"[{label(aid)} error] {e}",
            parallel_round=parallel_round,
        )


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
    run_meta: dict[str, Any] | None = None,
    context_log: list[dict[str, Any]] | None = None,
    efficiency_mode: bool = False,
    extra_follow_up: str = "",
) -> list[ChatMessage]:
    """Call selected agents for one round (round 1 parallel; round 2+ sequential for all modes)."""
    active = agents or available_agents()
    if not active:
        raise RuntimeError("No agents available. Configure CURSOR_API_KEY, codex login, or claude login.")
    active = active[:MAX_AGENTS_PER_ROUND]
    ordered = _round_agent_order(
        active,
        review_mode=review_mode,
        parallel_round=parallel_round,
        run_meta=run_meta,
    )
    review_advocate = _review_advocate(active, human_turn_index) if review_mode else None

    check_cancelled()
    replies: list[ChatMessage] = []
    sequential = parallel_round >= 2
    from agent_lab.room_team_orchestration import team_r1_split

    parallel_batch, lead_tail = (
        team_r1_split([str(a) for a in ordered], run_meta)
        if parallel_round == 1 and not review_mode and run_meta
        else ([str(a) for a in ordered], [])
    )
    use_lead_last_r1 = parallel_round == 1 and not review_mode and lead_tail and len(parallel_batch) < len(ordered)

    if use_lead_last_r1:
        check_cancelled()
        thread = list(messages)
        if parallel_batch:
            with ThreadPoolExecutor(max_workers=len(parallel_batch)) as pool:
                futures = {
                    pool.submit(
                        _invoke_agent_for_round,
                        aid,
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
                    ): aid
                    for aid in parallel_batch
                }
                try:
                    for fut in as_completed(futures):
                        check_cancelled()
                        replies.append(fut.result())
                except RoomRunCancelled:
                    pass
            thread = list(messages) + replies
        for aid in lead_tail:
            check_cancelled()
            try:
                msg = _invoke_agent_for_round(
                    str(aid),
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
                idle_peer = _teammate_idle_peer_message(str(aid), run_meta, parallel_round=parallel_round)
                if idle_peer:
                    replies.append(idle_peer)
                    thread.append(idle_peer)
            except RoomRunCancelled:
                break
        for aid in parallel_batch:
            idle_peer = _teammate_idle_peer_message(aid, run_meta, parallel_round=parallel_round)
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
                idle_peer = _teammate_idle_peer_message(aid, run_meta, parallel_round=parallel_round)
                if idle_peer:
                    replies.append(idle_peer)
                    thread.append(idle_peer)
        except RoomRunCancelled:
            pass
        return replies

    with ThreadPoolExecutor(max_workers=len(ordered)) as pool:
        futures = {
            pool.submit(
                _invoke_agent_for_round,
                aid,
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
            ): aid
            for aid in ordered
        }
        for fut in as_completed(futures):
            check_cancelled()
            replies.append(fut.result())
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
    run_meta: dict[str, Any] | None = None,
    context_log: list[dict[str, Any]] | None = None,
    efficiency_mode: bool = False,
) -> list[ChatMessage]:
    """Run multiple parallel waves; later waves see earlier agents' replies in the thread."""
    from agent_lab.room_team_orchestration import normalize_turn_profile

    profile = normalize_turn_profile(run_meta.get("turn_profile") if run_meta else None)
    n = max(1, min(parallel_rounds, MAX_AGENT_PARALLEL_ROUNDS))
    if profile == "specialist":
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
                active_agents=list(agents or available_agents())[:MAX_AGENTS_PER_ROUND],
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
):
    """Build agent context without calling an LLM. Returns (payload str, ContextBundle)."""
    if not folder.is_dir():
        raise FileNotFoundError(f"session not found: {folder}")
    topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
    messages = load_session_messages(folder)
    plan_md, run_meta = _session_context(folder)
    active = agents or available_agents()
    active = active[:MAX_AGENTS_PER_ROUND]
    human_turn_index = max(0, _human_turn_count(messages) - 1)
    review_advocate = _review_advocate(active, human_turn_index) if review_mode else None
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


def format_thread_numbered(messages: list[ChatMessage]) -> str:
    """Thread with chat.jsonl line numbers for scribe provenance."""
    lines: list[str] = []
    for i, m in enumerate(messages, start=1):
        if m.role == "user":
            lines.append(f"L{i} Human:\n{m.content}\n")
        elif m.role == "agent" and m.agent:
            lines.append(f"L{i} {label(m.agent)}:\n{m.content}\n")
        else:
            lines.append(f"L{i} System:\n{m.content}\n")
    return "\n".join(lines)


def synthesize_plan(
    topic: str,
    messages: list[ChatMessage],
    backend_agent: AgentId | None = None,
    *,
    run_meta: dict[str, Any] | None = None,
) -> str:
    """Scribe pass using one agent backend."""
    from agent_lab.room_context import scribe_thread_block
    from agent_lab.room_scribe_enrichment import (
        build_scribe_enrichment,
        format_scribe_agent_summaries_block,
    )

    agent: AgentId = backend_agent or _default_scribe_agent()
    latest_human = ""
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user >= 0:
        latest_human = (messages[last_user].content or "").strip()

    summaries_block = format_scribe_agent_summaries_block(messages, run_meta)
    if summaries_block.strip():
        agent_input = summaries_block
    else:
        numbered = scribe_thread_block(messages)
        agent_input = (
            f"Numbered conversation (fallback — no agent replies; use L{{n}} as chat.jsonl#L{{n}} refs):\n\n{numbered}"
        )

    user = (
        f"Human topic:\n{topic.strip()}\n\n"
        f"---\n\nLatest human message:\n{latest_human or '(none)'}\n\n"
        f"---\n\n{agent_input}\n\n---\n\nWrite the final plan.md content."
    )
    enrichment = build_scribe_enrichment(run_meta, messages)
    if enrichment.strip():
        user = f"{user}\n\n---\n\n{enrichment.strip()}"
    folder_raw = (run_meta or {}).get("_session_folder")
    if folder_raw:
        from agent_lab.plan_workflow import build_clarify_context_block

        clarify_block = build_clarify_context_block(Path(str(folder_raw)))
        if clarify_block.strip():
            user = f"{user}\n\n---\n\n{clarify_block.strip()}"
    return call_agent(agent, room_scribe_prompt(run_meta), user, scribe=True)


def auto_plan_scribe_enabled() -> bool:
    """Every completed turn re-synthesizes plan.md (disable via AGENT_LAB_AUTO_PLAN_SCRIBE=0)."""
    raw = os.getenv("AGENT_LAB_AUTO_PLAN_SCRIBE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _should_scribe_plan_after_turn(
    *,
    synthesize: bool,
    cancelled: bool,
    run_meta: dict[str, Any] | None = None,
    user_plan_send: bool = False,
) -> bool:
    if cancelled:
        return False
    from agent_lab.plan_workflow import (
        is_plan_workflow_active,
        plan_workflow_allows_auto_scribe,
        plan_workflow_allows_scribe,
    )

    if is_plan_workflow_active(run_meta):
        return plan_workflow_allows_scribe(
            run_meta,
            synthesize=synthesize,
            user_plan_send=user_plan_send,
        )
    return synthesize or plan_workflow_allows_auto_scribe(run_meta)


def _plan_trigger_for_turn(*, synthesize: bool, scribe_applied: bool) -> str | None:
    if not scribe_applied:
        return None
    return "plan_turn" if synthesize else "auto_turn"


def _read_plan_before(folder: Path | None) -> str:
    if folder is None:
        return ""
    plan_path = folder / "plan.md"
    if not plan_path.is_file():
        return ""
    return plan_path.read_text(encoding="utf-8")


def _bootstrap_session_folder_for_plan_workflow(
    topic: str,
    *,
    base: Path | None,
    synthesize: bool,
) -> Path | None:
    """Create on-disk session folder before first agent round (plan workflow needs run.json)."""
    from agent_lab.plan_workflow import (
        init_plan_workflow_on_plan_send,
        should_enable_plan_workflow,
    )
    from agent_lab.session import session_dir

    if not should_enable_plan_workflow(synthesize=synthesize):
        return None
    folder = session_dir(topic, base=base or SESSIONS_DIR)
    (folder / "topic.txt").write_text(topic.strip() + "\n", encoding="utf-8")
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    return folder


def _plan_workflow_post_agent_turn(
    folder: Path,
    *,
    topic: str,
    messages: list[ChatMessage],
    run_meta: dict[str, Any],
    plan_before: str,
    mode: str,
    synthesize: bool,
    cancelled: bool,
    active_agents: list[Any],
    permissions: dict | None,
    on_event: OnAgentEvent | None,
) -> tuple[str, bool, dict[str, Any]]:
    """Tick plan FSM, optional scribe, peer-review pipeline after agent replies."""
    from agent_lab.human_inbox import has_pending_question
    from agent_lab.plan_workflow import (
        emit_plan_workflow_phase_if_changed,
        is_plan_workflow_active,
        orchestrate_plan_workflow_pipeline,
        plan_workflow_phase,
        plan_workflow_should_advance_on_turn,
        tick_plan_workflow_after_turn,
    )
    from agent_lab.run_meta import read_run_meta

    plan_md = plan_before
    pw_force_scribe = False
    pw_active = is_plan_workflow_active(run_meta)
    pw_advance = plan_workflow_should_advance_on_turn(run_meta, synthesize=synthesize)
    phase_before = plan_workflow_phase(run_meta) if pw_active else None
    if pw_active and pw_advance and not cancelled:
        pw_tick = tick_plan_workflow_after_turn(
            folder,
            synthesize=synthesize,
            cancelled=cancelled,
            plan_md=plan_md,
            plan_before=plan_before,
            has_pending_inbox_question=has_pending_question(run_meta),
        )
        if pw_tick.get("wait_inbox") and on_event:
            on_event("inbox_pending", {"phase": "CLARIFY"})
        if pw_tick.get("advance") == "DRAFT":
            pw_force_scribe = True
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)

    scribe_applied = (
        _should_scribe_plan_after_turn(
            synthesize=synthesize,
            cancelled=cancelled,
            run_meta=run_meta,
            user_plan_send=synthesize,
        )
        or pw_force_scribe
    )
    if scribe_applied:
        plan_md = _apply_scribe_after_turn(
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            plan_before=plan_before,
            mode=mode,
            scribe=True,
            user_plan_send=synthesize,
            cancelled=cancelled,
            on_event=on_event,
            session_folder=folder,
            plan_trigger="plan_turn" if synthesize else "auto_turn",
        )
    if pw_advance and is_plan_workflow_active(run_meta) and not cancelled and scribe_applied:
        plan_md, pw_replies, pw_meta = orchestrate_plan_workflow_pipeline(
            folder,
            topic=topic,
            messages=messages,
            plan_md=plan_md,
            plan_before=plan_before,
            synthesize=synthesize,
            cancelled=cancelled,
            agents=[str(a) for a in active_agents],
            permissions=permissions,
            run_meta=run_meta,
            on_event=on_event,
        )
        if pw_replies:
            messages.extend(pw_replies)
        if pw_meta.get("pending_approval") and on_event:
            on_event(
                "plan_workflow_pending",
                {"phase": plan_workflow_phase(read_run_meta(folder))},
            )
    if pw_active:
        run_meta = read_run_meta(folder)
        emit_plan_workflow_phase_if_changed(
            folder,
            on_event,
            phase_before,
            plan_workflow_phase(run_meta),
        )
    return plan_md, scribe_applied, run_meta


def _apply_scribe_after_turn(
    *,
    topic: str,
    messages: list[ChatMessage],
    run_meta: dict[str, Any] | None,
    plan_before: str,
    mode: str,
    scribe: bool,
    user_plan_send: bool,
    cancelled: bool,
    on_event: OnAgentEvent | None,
    session_folder: Path | None = None,
    plan_trigger: str | None = None,
) -> str:
    """Run scribe, patch objections only (E2b), or leave plan unchanged."""
    if not scribe or cancelled:
        return plan_before
    if not messages:
        return plan_before
    from agent_lab.room_scribe_enrichment import (
        patch_plan_objections_only,
        should_skip_scribe_for_open_objections,
    )

    if should_skip_scribe_for_open_objections(run_meta, mode=mode, synthesize=user_plan_send):
        if on_event:
            on_event("scribe_skipped", {"reason": "open_objections_discuss"})
        return patch_plan_objections_only(plan_before, run_meta)
    if session_folder and run_meta is not None:
        from agent_lab.room_hooks import _hook_run_record, run_pre_scribe_hooks
        from agent_lab.run_meta import append_hook_run

        pre = run_pre_scribe_hooks(
            run_meta,
            session_folder=session_folder,
            session_id=str(run_meta.get("_session_id") or session_folder.name),
            trigger=plan_trigger or ("plan_turn" if user_plan_send else "auto_turn"),
            message_count=len(messages),
        )
        append_hook_run(
            session_folder,
            _hook_run_record(
                pre,
                session_id=str(run_meta.get("_session_id") or session_folder.name),
                human_turn=_human_turn_count(messages),
            ),
            run_meta=run_meta,
        )
        if pre.blocked:
            msg = pre.feedback.strip() or "pre_scribe hook blocked plan synthesis"
            if on_event:
                on_event("scribe_error", {"message": msg, "hook": "pre_scribe"})
            if not (plan_before or "").strip():
                return f"## Plan synthesis blocked\n\n{msg}"
            return plan_before
    if on_event:
        on_event("scribe_start", {})
    try:
        plan_md = synthesize_plan(topic, messages, run_meta=run_meta)
        _emit_plan_actions_validation(plan_md, on_event)
        if on_event:
            on_event("scribe_done", {"chars": len(plan_md)})
        return plan_md
    except Exception as e:
        if on_event:
            on_event("scribe_error", {"message": str(e)})
        if not (plan_before or "").strip():
            return f"## Plan synthesis failed\n\n{e}"
        return plan_before


def _default_scribe_agent() -> AgentId:
    raw = (os.getenv("ROOM_SCRIBE_AGENT") or "claude").strip().lower()
    if raw in AGENT_IDS and raw in available_agents():
        return raw  # type: ignore[return-value]
    for fallback in ("codex", "claude", "cursor"):
        if fallback in available_agents():
            return fallback  # type: ignore[return-value]
    return "claude"


def _emit_plan_actions_validation(
    plan_md: str,
    on_event: Callable[[str, dict[str, Any]], None] | None,
) -> dict[str, Any]:
    import logging

    from agent_lab.plan_actions import validate_plan_actions_format

    result = validate_plan_actions_format(plan_md)
    if on_event:
        on_event("plan_actions_validation", result)
    if not result.get("ok"):
        logging.getLogger("agent_lab.plan_actions").warning(
            "plan_actions_validation issues=%s",
            result.get("issues"),
        )
    return result


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


def _peer_metrics_for_messages(messages: list[ChatMessage]) -> dict[str, Any]:
    from agent_lab.room_turn_state import current_turn_slice, peer_turn_metrics

    turn_msgs, _ = current_turn_slice(messages)
    return peer_turn_metrics(turn_msgs)


def _final_turn_state_dict(
    messages: list[ChatMessage],
    *,
    run_meta: dict[str, Any] | None,
    active_agents: list[str],
    consensus_meta: dict[str, Any] | None,
    plan_md: str,
) -> dict[str, Any]:
    if run_meta and run_meta.get("turn_state"):
        return run_meta["turn_state"]  # type: ignore[return-value]
    from agent_lab.room_turn_state import current_turn_slice, derive_turn_state

    turn_msgs, line_base = current_turn_slice(messages)
    return derive_turn_state(
        turn_msgs,
        line_base=line_base,
        active_agents=active_agents,
        consensus=consensus_meta,
        plan_md=plan_md,
    ).to_dict()


def _turn_snapshot(
    *,
    mode: str,
    synthesize: bool,
    agents_used: list[str],
    parallel_rounds: int,
    permissions: dict | None,
    latency_ms: int,
    status: str = "completed",
    synthesize_only: bool = False,
    plan_trigger: str | None = None,
    request_id: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    review_mode: bool = False,
    review_advocate: str | None = None,
    context_log: list[dict[str, Any]] | None = None,
    consensus_mode: bool = False,
    consensus: dict[str, Any] | None = None,
    efficiency_mode: bool = False,
    turn_state: dict[str, Any] | None = None,
    turn_profile: str | None = None,
    plan_sync_summary: str | None = None,
    turn_lead: str | None = None,
    turn_leads: dict[str, str] | None = None,
    send_receipt: str | None = None,
    peer_message_count: int | None = None,
    agents_with_r2_reply: list[str] | None = None,
    failed_agents: list[str] | None = None,
    succeeded_agents: list[str] | None = None,
    last_delegate: dict[str, Any] | None = None,
    communicate_meta: dict[str, Any] | None = None,
    category: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from agent_lab.invoke import model_name

    snap: dict[str, Any] = {
        "mode": mode,
        "synthesize": synthesize,
        "agent_parallel_rounds": parallel_rounds,
        "agents": agents_used,
        "permissions": permissions or {},
        "model": model_name(),
        "latency_ms": latency_ms,
        "status": status,
    }
    if context_log:
        snap["context"] = {
            "agents": context_log,
            "payload_chars_total": sum((entry.get("layer_chars") or {}).get("total", 0) for entry in context_log),
            "summary": summarize_turn_context(context_log),
        }
        snap["models"] = {entry["agent"]: entry.get("model", "") for entry in context_log if entry.get("agent")}
    if synthesize_only:
        snap["synthesize_only"] = True
    if plan_trigger:
        snap["plan_trigger"] = plan_trigger
    if request_id:
        snap["request_id"] = request_id
    if started_at:
        snap["started_at"] = started_at
    if completed_at:
        snap["completed_at"] = completed_at
    if review_mode:
        snap["review_mode"] = True
        if review_advocate:
            snap["review_advocate"] = review_advocate
    if consensus_mode:
        snap["consensus_mode"] = True
        if consensus:
            snap["consensus"] = consensus
    if efficiency_mode:
        snap["efficiency_mode"] = True
    if turn_state:
        snap["turn_state"] = turn_state
    if turn_profile and turn_profile in (
        "quick",
        "analyze",
        "discuss",
        "review",
        "free",
        "specialist",
        "verified",
    ):
        snap["turn_profile"] = "analyze" if turn_profile == "discuss" else turn_profile
    if plan_sync_summary:
        snap["plan_sync_summary"] = plan_sync_summary
    if turn_lead:
        snap["turn_lead"] = turn_lead
    if turn_leads:
        snap["turn_leads"] = turn_leads
    if send_receipt:
        snap["send_receipt"] = send_receipt
    if peer_message_count is not None:
        snap["peer_message_count"] = peer_message_count
    if agents_with_r2_reply:
        snap["agents_with_r2_reply"] = list(agents_with_r2_reply)
    if failed_agents:
        snap["failed_agents"] = list(failed_agents)
    if succeeded_agents:
        snap["succeeded_agents"] = list(succeeded_agents)
    if last_delegate:
        snap["last_delegate"] = dict(last_delegate)
    if communicate_meta:
        snap["communicate_meta"] = communicate_meta
    if category:
        snap["category"] = dict(category)
    return snap


def consensus_reached(consensus_meta: dict[str, Any] | None) -> bool:
    """True when free-discuss consensus loop finished with full agreement."""
    return bool(consensus_meta and consensus_meta.get("status") == "reached")


def _post_plan_scribe_inbox_harvest(
    folder: Path,
    *,
    plan_md: str,
    trigger: str,
    verified_at: str | None = None,
    verified_excerpt: str | None = None,
    verified_summary: str | None = None,
) -> None:
    """After auto plan scribe: T-Q2 + T-B1 inbox harvest (discuss-mode gates)."""
    from agent_lab.inbox_harvest import (
        _supersede_legacy_verified_build_items,
        harvest_post_plan_inbox,
    )
    from agent_lab.run_meta import patch_run_meta

    messages = load_session_messages(folder)
    human_turn = _human_turn_count(messages)

    def _patch(run_meta: dict[str, Any]) -> dict[str, Any]:
        if trigger == "verified_loop_done":
            _supersede_legacy_verified_build_items(run_meta)
        harvest_post_plan_inbox(
            run_meta,
            messages,
            plan_md=plan_md,
            human_turn=human_turn,
        )
        if trigger == "verified_loop_done" and verified_at:
            run_meta["verified_plan_sync"] = {
                "verified_at": verified_at,
                "summary": verified_summary or "",
                "excerpt": verified_excerpt or "",
                "ts": _now(),
            }
        from agent_lab.human_inbox import compute_inbox_pending

        run_meta["inbox_pending"] = compute_inbox_pending(run_meta)
        return run_meta

    patch_run_meta(folder, _patch)

    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    dispatch(folder, RuntimeEvent.SCRIBE_COMPLETE, {"plan_md": plan_md})


def _emit_plan_pipeline_proposal(
    folder: Path,
    *,
    excerpt: str,
    summary: str,
    notice: str,
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    trigger: str,
) -> None:
    if not on_event:
        return
    synced_event = "verified_plan_synced" if trigger == "verified_loop_done" else "consensus_plan_synced"
    on_event(
        synced_event,
        {
            "excerpt": excerpt,
            "summary": summary,
            "notice": notice,
            "trigger": trigger,
        },
    )
    from agent_lab.runtime.invoke_execute import list_plan_actions

    actions_info = list_plan_actions(folder, permissions=permissions)
    recommended = actions_info.get("recommended")
    has_executable = recommended is not None
    action_key = recommended.get("action_key") if recommended else None
    on_event(
        "consensus_dry_run_proposal",
        {
            "excerpt": excerpt,
            "summary": summary,
            "notice": notice,
            "recommended": recommended,
            "has_executable": has_executable,
            "action_key": action_key,
            "trigger": trigger,
        },
    )


def synthesize_session_plan(
    folder: Path,
    *,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    request_id: str | None = None,
    trigger: str = "synthesize_only",
    previous_plan_md: str | None = None,
) -> tuple[str, str]:
    """Re-synthesize plan.md from existing chat without a new agent round."""
    from agent_lab.plan_sync_summary import summarize_plan_changes

    if not folder.is_dir():
        raise FileNotFoundError(f"session not found: {folder}")
    plan_path = folder / "plan.md"
    old_plan = previous_plan_md
    if old_plan is None and plan_path.is_file():
        old_plan = plan_path.read_text(encoding="utf-8")
    if request_id and _find_completed_synthesize(folder, request_id):
        if plan_path.is_file():
            if on_event:
                on_event("scribe_skipped", {"reason": "duplicate_request_id"})
            current = plan_path.read_text(encoding="utf-8")
            return current, summarize_plan_changes(old_plan or "", current)
        raise FileNotFoundError("plan.md not found")
    topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
    messages = load_session_messages(folder)
    if not messages:
        raise ValueError("no messages to synthesize")
    started_at = _now()
    t0 = time.perf_counter()
    run_meta_snapshot = _read_run_meta(folder)
    from agent_lab.room_hooks import _hook_run_record, run_pre_scribe_hooks
    from agent_lab.run_meta import append_hook_run

    pre = run_pre_scribe_hooks(
        run_meta_snapshot,
        session_folder=folder,
        session_id=folder.name,
        trigger=trigger,
        message_count=len(messages),
    )
    append_hook_run(
        folder,
        _hook_run_record(pre, session_id=folder.name),
        run_meta=run_meta_snapshot,
    )
    if pre.blocked:
        msg = pre.feedback.strip() or "pre_scribe hook blocked plan synthesis"
        if on_event:
            on_event("scribe_error", {"message": msg, "hook": "pre_scribe"})
        raise RuntimeError(msg)
    if on_event:
        on_event("scribe_start", {})
    try:
        plan_md = synthesize_plan(topic, messages, run_meta=_read_run_meta(folder))
        _emit_plan_actions_validation(plan_md, on_event)
        if on_event:
            on_event("scribe_done", {"chars": len(plan_md)})
    except Exception as e:
        if on_event:
            on_event("scribe_error", {"message": str(e)})
        raise
    plan_sync_summary = summarize_plan_changes(old_plan or "", plan_md)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    completed_at = _now()
    existing_meta: dict[str, Any] = {}
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    agents_used = existing_meta.get("agents") or [a for a in available_agents()]
    _write_session_files(
        folder,
        topic,
        messages,
        plan_md,
        agents_used=agents_used,
        merge_meta={**existing_meta, "topic": topic},
        turn_meta=_turn_snapshot(
            mode="plan",
            synthesize=True,
            agents_used=agents_used,
            parallel_rounds=0,
            permissions=permissions,
            latency_ms=latency_ms,
            synthesize_only=True,
            plan_trigger=trigger,
            request_id=request_id,
            started_at=started_at,
            completed_at=completed_at,
            plan_sync_summary=plan_sync_summary,
            send_receipt="plan_updated",
        ),
    )
    return plan_md, plan_sync_summary


def maybe_auto_scribe_after_consensus(
    folder: Path,
    *,
    consensus_meta: dict[str, Any] | None,
    synthesize: bool,
    cancelled: bool,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
) -> str | None:
    """After discuss+consensus, auto-scribe plan.md and notify what was reflected."""
    from agent_lab.consensus_agreements import (
        agreement_plan_synced_notice,
        consensus_topic_excerpt,
    )

    if cancelled or not consensus_reached(consensus_meta):
        return None

    excerpt = consensus_topic_excerpt(consensus_meta)
    plan_path = folder / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""

    from agent_lab.consensus_agreements import pending_consensus_agreements
    from agent_lab.run_meta import read_run_meta

    run = read_run_meta(folder)
    pending = pending_consensus_agreements(run.get("consensus_agreements"))
    if not pending:
        if plan_md.strip():
            return plan_md
        return None

    if on_event:
        on_event("consensus_plan_sync_start", {"excerpt": excerpt})

    old_plan = plan_md
    try:
        plan_md, summary = synthesize_session_plan(
            folder,
            on_event=on_event,
            permissions=permissions,
            trigger="consensus_reached",
            previous_plan_md=old_plan,
        )
        current_plan = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
        if current_plan != plan_md:
            plan_path.write_text(plan_md, encoding="utf-8")
    except Exception as e:
        if on_event:
            on_event(
                "consensus_plan_sync_failed",
                {"excerpt": excerpt, "message": str(e)},
            )
            on_event(
                "scribe_error",
                {"message": str(e), "auto": True, "excerpt": excerpt},
            )
        return None

    _post_plan_scribe_inbox_harvest(
        folder,
        plan_md=plan_md,
        trigger="consensus_reached",
    )

    from agent_lab.consensus_agreements import mark_agreements_plan_synced
    from agent_lab.run_meta import patch_run_meta

    messages = load_session_messages(folder)

    def _mark_agreements_synced(run_meta: dict[str, Any]) -> dict[str, Any]:
        run_meta["consensus_agreements"] = mark_agreements_plan_synced(
            run_meta.get("consensus_agreements"),
            message_count=len(messages),
            synced_at=_now(),
        )
        return run_meta

    patch_run_meta(folder, _mark_agreements_synced)

    notice = agreement_plan_synced_notice(excerpt, summary)
    _emit_plan_pipeline_proposal(
        folder,
        excerpt=excerpt,
        summary=summary,
        notice=notice,
        permissions=permissions,
        on_event=on_event,
        trigger="consensus_reached",
    )
    return plan_md


def maybe_auto_scribe_after_verified_loop(
    folder: Path,
    *,
    verified_result: dict[str, Any] | None,
    cancelled: bool,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
) -> str | None:
    """After Oracle VERIFIED, auto-scribe plan.md then harvest Question + Build."""
    from agent_lab.consensus_agreements import agreement_plan_synced_notice
    from agent_lab.run_meta import read_run_meta

    if cancelled or not verified_result:
        return None
    loop = dict(verified_result.get("verified_loop") or {})
    if str(loop.get("status") or "") != "done":
        return None

    verified_at = str(loop.get("verified_at") or "").strip()
    run = read_run_meta(folder)
    sync = dict(run.get("verified_plan_sync") or {})
    if sync.get("verified_at") == verified_at:
        return None

    loop_goal = dict(loop.get("loop_goal") or {})
    excerpt = str(loop_goal.get("text") or "").strip()[:200] or "Verified loop"

    plan_path = folder / "plan.md"
    old_plan = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""

    if on_event:
        on_event("verified_plan_sync_start", {"excerpt": excerpt})

    try:
        plan_md, summary = synthesize_session_plan(
            folder,
            on_event=on_event,
            permissions=permissions,
            trigger="verified_loop_done",
            previous_plan_md=old_plan,
        )
        current_plan = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
        if current_plan != plan_md:
            plan_path.write_text(plan_md, encoding="utf-8")
    except Exception as e:
        if on_event:
            on_event(
                "verified_plan_sync_failed",
                {"excerpt": excerpt, "message": str(e)},
            )
            on_event(
                "scribe_error",
                {
                    "message": str(e),
                    "auto": True,
                    "excerpt": excerpt,
                    "trigger": "verified_loop_done",
                },
            )
        return None

    _post_plan_scribe_inbox_harvest(
        folder,
        plan_md=plan_md,
        trigger="verified_loop_done",
        verified_at=verified_at,
        verified_excerpt=excerpt,
        verified_summary=summary,
    )

    notice = agreement_plan_synced_notice(excerpt, summary)
    _emit_plan_pipeline_proposal(
        folder,
        excerpt=excerpt,
        summary=summary,
        notice=notice,
        permissions=permissions,
        on_event=on_event,
        trigger="verified_loop_done",
    )
    return plan_md


def ensure_consensus_plan_sync(folder: Path) -> bool:
    """Backfill plan → question → build for unreconciled consensus agreements."""
    from agent_lab.consensus_agreements import pending_consensus_agreements
    from agent_lab.run_meta import read_run_meta

    run = read_run_meta(folder)
    pending = pending_consensus_agreements(run.get("consensus_agreements"))
    if not pending:
        return False
    latest = pending[-1]
    excerpt = str(latest.get("excerpt") or "").strip()
    if not excerpt:
        return False
    result = maybe_auto_scribe_after_consensus(
        folder,
        consensus_meta={"status": "reached", "anchor": {"excerpt": excerpt}},
        synthesize=False,
        cancelled=False,
        on_event=None,
        permissions=None,
    )
    return result is not None


def ensure_verified_plan_sync(folder: Path) -> bool:
    """Backfill plan → question → build after Oracle VERIFIED (idempotent)."""
    from agent_lab.run_meta import read_run_meta

    run = read_run_meta(folder)
    loop = dict(run.get("verified_loop") or {})
    if str(loop.get("status") or "") != "done":
        return False
    sync = dict(run.get("verified_plan_sync") or {})
    if sync.get("verified_at") == loop.get("verified_at"):
        return False
    result = maybe_auto_scribe_after_verified_loop(
        folder,
        verified_result={"verified_loop": loop},
        cancelled=False,
        on_event=None,
        permissions=None,
    )
    return result is not None


def ensure_session_plan_pipeline(folder: Path) -> bool:
    """Run pending consensus or verified plan auto-sync (best-effort)."""
    changed = ensure_consensus_plan_sync(folder)
    if ensure_verified_plan_sync(folder):
        changed = True
    return changed


def _try_dispatch_turn(
    *,
    body: str,
    topic: str,
    messages: list[ChatMessage],
    run_meta: dict[str, Any],
    folder: Path,
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    clarifier_questions: list[str] | None,
    human_turn_num: int,
) -> list[ChatMessage] | None:
    from agent_lab.room_dispatch import try_dispatch_turn

    replies = try_dispatch_turn(
        body=body,
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        folder=folder,
        permissions=permissions,
        on_event=on_event,
        clarifier_questions=clarifier_questions,
        human_turn=human_turn_num,
    )
    return replies  # type: ignore[return-value]


def _try_delegate_turn(
    *,
    body: str,
    topic: str,
    messages: list[ChatMessage],
    run_meta: dict[str, Any],
    folder: Path,
    permissions: dict | None,
    on_event: OnAgentEvent | None,
    clarifier_questions: list[str] | None,
    human_turn_num: int,
) -> list[ChatMessage] | None:
    return _try_dispatch_turn(
        body=body,
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        folder=folder,
        permissions=permissions,
        on_event=on_event,
        clarifier_questions=clarifier_questions,
        human_turn_num=human_turn_num,
    )


def _delegate_run_meta_patch(run_meta: dict[str, Any]) -> dict[str, Any] | None:
    from agent_lab.room_dispatch import dispatch_run_meta_patch

    return dispatch_run_meta_patch(run_meta)


def _communicate_meta_for_turn(
    replies: list[ChatMessage],
    context_log: list[dict[str, Any]] | None,
    *,
    parallel_rounds: int,
    review_mode: bool,
    consensus_mode: bool,
    turn_profile: str | None,
    efficiency_mode: bool,
) -> dict[str, Any]:
    from agent_lab.reply_policy import resolve_reply_policy, summarize_turn_communicate_meta

    policy = resolve_reply_policy(
        parallel_round=parallel_rounds,
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile or "",
        efficiency_mode=efficiency_mode,
    )
    return summarize_turn_communicate_meta(replies, context_log, policy=policy)


def _goal_auto_continue_message(result: dict[str, Any] | None) -> str | None:
    if not result or (result.get("check") or {}).get("verdict") != "fail":
        return None
    loop = result.get("goal_loop") or {}
    if len(loop.get("checks") or []) >= int(loop.get("max_checks") or 0):
        return None
    return str(loop.get("continue_prompt") or "").strip() or None


def _verified_loop_continue_message(result: dict[str, Any] | None) -> str | None:
    if not result or not result.get("handled"):
        return None
    loop = result.get("verified_loop") or {}
    if loop.get("status") in {"done", "failed", "cancelled", "pending_approval"}:
        return None
    if result.get("circuit_breaker"):
        return None
    return str(result.get("continue_prompt") or "").strip() or None


def _verified_loop_complete_payload(result: dict[str, Any] | None) -> dict[str, Any]:
    if not result:
        return {}
    loop = result.get("verified_loop") or {}
    return {
        "verified_loop": loop,
        "verified_loop_pending": bool(result.get("verified_loop_pending")),
        "verified_loop_status": loop.get("status"),
        "verified_loop_circuit_breaker": bool(result.get("circuit_breaker")),
    }


def _maybe_verified_loop_after_turn(
    folder: Path,
    messages: list[ChatMessage],
    turn_profile: str | None,
    *,
    cancelled: bool = False,
) -> dict[str, Any] | None:
    from agent_lab.verified_loop import maybe_handle_verified_loop_after_turn

    return maybe_handle_verified_loop_after_turn(
        folder,
        messages,
        turn_profile,
        cancelled=cancelled,
    )


def continue_room_round(
    folder: Path,
    user_message: str,
    *,
    agents: list[AgentId] | None = None,
    synthesize: bool = False,
    parallel_rounds: int = DEFAULT_AGENT_PARALLEL_ROUNDS,
    on_event: OnAgentEvent | None = None,
    permissions: dict | None = None,
    review_mode: bool = False,
    consensus_mode: bool = False,
    efficiency_mode: bool = False,
    turn_profile: str | None = None,
    research_mode: bool = False,
    _goal_auto_continue_depth: int = 0,
    _verified_loop_depth: int = 0,
) -> tuple[list[ChatMessage], str]:
    """Append a user turn + parallel agent replies to an existing session."""
    if not folder.is_dir():
        raise FileNotFoundError(f"session not found: {folder}")
    topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
    messages = load_session_messages(folder)
    body = user_message.strip()
    att = describe_attachments(folder)
    if att:
        body = f"{body}\n\n---\n\n{att}"
    human_turn_index = _human_turn_count(messages)
    messages.append(ChatMessage(role="user", agent=None, content=body))
    human_turn_num = _human_turn_count(messages)
    from agent_lab.human_inbox import supersede_pending_inbox
    from agent_lab.mission_board import begin_human_turn

    begin_human_turn(folder, human_turn=human_turn_num)
    supersede_pending_inbox(folder, human_turn_id=human_turn_num)
    plan_md, run_meta = _session_context(folder)
    from agent_lab.inbox_harvest import clear_inbox_fork_grace

    clear_inbox_fork_grace(run_meta)
    _bind_session_to_run_meta(run_meta, folder)
    active_agents = [a for a in (agents or available_agents())]
    mode = "plan" if synthesize else "discuss"
    review_advocate = _review_advocate(active_agents, human_turn_index) if review_mode and active_agents else None
    from agent_lab.room_team_orchestration import resolve_turn_lead

    resolve_turn_lead(
        run_meta,
        human_turn_num,
        [str(a) for a in active_agents],
        user_message=body,
    )
    _set_active_turn_flags(
        run_meta,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
    from agent_lab.plan_workflow import (
        init_plan_workflow_on_plan_send,
        plan_workflow_skips_server_clarifier,
        should_enable_plan_workflow,
    )

    if should_enable_plan_workflow(synthesize=synthesize):
        init_plan_workflow_on_plan_send(folder)
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)
    if turn_profile:
        tp = (turn_profile or "analyze").strip().lower()
        run_meta["turn_profile"] = "analyze" if tp == "discuss" else tp
        if run_meta["turn_profile"] == "specialist":
            from agent_lab.room_agent_capabilities import ensure_specialist_capabilities

            if not run_meta.get("agent_capabilities_custom"):
                ensure_specialist_capabilities(run_meta)
            parallel_rounds = max(parallel_rounds, 2)
        from agent_lab.plan_workflow import apply_legacy_verified_turn_profile

        apply_legacy_verified_turn_profile(folder, run_meta, synthesize=synthesize)
    if research_mode or run_meta.get("turn_profile") == "specialist":
        run_meta["research_mode"] = True
    from agent_lab.session_clarifier import (
        build_clarifier_interview,
        interview_prompts,
        persist_clarifier_interview,
        sync_clarifier_answers_from_inbox,
    )

    sync_clarifier_answers_from_inbox(folder)
    skip_server_clarifier = plan_workflow_skips_server_clarifier(run_meta)
    clarifier_interview = None
    clarifier_questions: list[str] | None = None
    if not skip_server_clarifier:
        clarifier_interview = build_clarifier_interview(
            body,
            is_new_session=False,
            human_message_count=human_turn_num,
            plan_mode=synthesize,
        )
        clarifier_questions = interview_prompts(clarifier_interview)
        if clarifier_interview:
            persist_clarifier_interview(folder, clarifier_interview)
        if clarifier_questions and on_event:
            on_event(
                "clarifier_prompt",
                {"questions": clarifier_questions, "interview": clarifier_interview},
            )
    t0 = time.perf_counter()
    context_log: list[dict[str, Any]] = []
    _prepare_team_coordination_before_round(
        folder,
        run_meta,
        active_agents,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
    consensus_meta: dict[str, Any] | None = None
    replies: list[ChatMessage] = []
    cancelled = False
    plan_before = (folder / "plan.md").read_text(encoding="utf-8") if (folder / "plan.md").is_file() else ""
    delegate_replies = _try_delegate_turn(
        body=body,
        topic=topic,
        messages=messages,
        run_meta=run_meta,
        folder=folder,
        permissions=permissions,
        on_event=on_event,
        clarifier_questions=clarifier_questions,
        human_turn_num=human_turn_num,
    )
    try:
        if clarifier_questions:
            replies = []
        elif delegate_replies is not None:
            replies = delegate_replies
            parallel_rounds = 1
        elif consensus_mode:
            replies, consensus_meta = run_consensus_agent_rounds(
                topic,
                messages,
                agents=agents,
                on_event=on_event,
                permissions=permissions,
                human_turn_index=human_turn_index,
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
            parallel_rounds = consensus_meta.get("rounds", 1) if consensus_meta else 1
            if consensus_meta is not None and run_meta.get("_turn_category"):
                consensus_meta.setdefault("category", run_meta["_turn_category"])
        else:
            replies = run_agent_rounds(
                topic,
                messages,
                agents=agents,
                parallel_rounds=parallel_rounds,
                on_event=on_event,
                permissions=permissions,
                review_mode=review_mode,
                human_turn_index=human_turn_index,
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
    except RoomRunCancelled:
        cancelled = True
    if cancelled or is_cancelled():
        cancelled = True
        if on_event:
            on_event("run_cancelled", {"message": "답변 중지됨"})
    messages.extend(replies)
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
    latency_ms = int((time.perf_counter() - t0) * 1000)
    turn_summary = _agent_turn_summary(replies)
    turn_status = _turn_status_from_replies(
        replies,
        cancelled=cancelled,
        consensus_meta=consensus_meta,
        consensus_mode=consensus_mode,
    )
    _emit_turn_terminal_status(
        status=turn_status,
        replies=replies,
        on_event=on_event,
        consensus_mode=consensus_mode,
    )
    _finalize_durable_turn(folder, human_turn_num, turn_status)
    existing_meta: dict[str, Any] = {}
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    from agent_lab.room_tasks import team_lead
    from agent_lab.room_team_orchestration import resolve_send_receipt, turn_leads_map
    from agent_lab.plan_workflow import is_plan_workflow_active, plan_workflow_complete_payload, plan_workflow_phase

    plan_updated = bool(not cancelled and scribe_applied and plan_md and plan_md != plan_before)
    pw_phase = plan_workflow_phase(run_meta) if is_plan_workflow_active(run_meta) else None
    peer = _peer_metrics_for_messages(messages)
    send_receipt_val = resolve_send_receipt(
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        plan_updated=plan_updated,
        status=turn_status,
        plan_workflow_phase=pw_phase,
    )
    communicate_meta = _communicate_meta_for_turn(
        replies,
        context_log,
        parallel_rounds=parallel_rounds,
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile or str(run_meta.get("turn_profile") or ""),
        efficiency_mode=efficiency_mode,
    )
    from agent_lab.goal_loop import (
        goal_auto_continue_enabled,
        maybe_check_session_goal_after_turn,
    )
    from agent_lab.plan_workflow import plan_workflow_skips_goal_check
    from agent_lab.verified_loop import normalize_verified_profile

    active_profile = turn_profile or run_meta.get("turn_profile")
    verified_result = _maybe_verified_loop_after_turn(
        folder,
        messages,
        active_profile,
        cancelled=cancelled,
    )
    verified_continue = None if cancelled else _verified_loop_continue_message(verified_result)
    _write_session_files(
        folder,
        topic,
        messages,
        plan_md,
        agents_used=active_agents,
        merge_meta={**existing_meta, "topic": topic},
        turn_meta=_turn_snapshot(
            mode=mode,
            synthesize=synthesize,
            agents_used=active_agents,
            parallel_rounds=parallel_rounds,
            permissions=permissions,
            latency_ms=latency_ms,
            status=turn_status,
            review_mode=review_mode,
            review_advocate=review_advocate,
            context_log=context_log,
            consensus_mode=consensus_mode,
            consensus=consensus_meta,
            efficiency_mode=efficiency_mode,
            turn_state=_final_turn_state_dict(
                messages,
                run_meta=run_meta,
                active_agents=active_agents,
                consensus_meta=consensus_meta,
                plan_md=plan_md,
            ),
            turn_profile=turn_profile,
            turn_lead=team_lead(run_meta),
            turn_leads=turn_leads_map(run_meta),
            send_receipt=send_receipt_val,
            peer_message_count=int(peer.get("peer_message_count") or 0),
            agents_with_r2_reply=list(peer.get("agents_with_r2_reply") or []),
            failed_agents=turn_summary["failed_agents"],
            succeeded_agents=turn_summary["succeeded_agents"],
            last_delegate=run_meta.get("last_delegate"),
            plan_trigger=plan_trigger,
            communicate_meta=communicate_meta,
            category=run_meta.get("_turn_category"),
        ),
        run_meta_patch=_delegate_run_meta_patch(run_meta),
        clarifier_questions=clarifier_questions,
    )
    if verified_continue and _verified_loop_depth < 3:
        return continue_room_round(
            folder,
            verified_continue,
            agents=active_agents,
            synthesize=False,
            parallel_rounds=1,
            on_event=on_event,
            permissions=permissions,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=efficiency_mode,
            turn_profile=active_profile or "verified",
            research_mode=research_mode,
            _goal_auto_continue_depth=_goal_auto_continue_depth,
            _verified_loop_depth=_verified_loop_depth + 1,
        )

    goal_result = None
    if not normalize_verified_profile(active_profile) and not plan_workflow_skips_goal_check(run_meta):
        goal_result = maybe_check_session_goal_after_turn(folder, messages)
    goal_continue = _goal_auto_continue_message(goal_result)
    if goal_auto_continue_enabled() and goal_continue and _goal_auto_continue_depth < 1:
        return continue_room_round(
            folder,
            goal_continue,
            agents=active_agents,
            synthesize=False,
            parallel_rounds=1,
            on_event=on_event,
            permissions=permissions,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=efficiency_mode,
            turn_profile="analyze",
            research_mode=research_mode,
            _goal_auto_continue_depth=1,
            _verified_loop_depth=_verified_loop_depth,
        )
    auto_plan = maybe_auto_scribe_after_verified_loop(
        folder,
        verified_result=verified_result,
        cancelled=cancelled,
        on_event=on_event,
        permissions=permissions,
    )
    if auto_plan is not None:
        plan_md = auto_plan
    elif not normalize_verified_profile(active_profile):
        auto_plan = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta=consensus_meta,
            synthesize=synthesize,
            cancelled=cancelled,
            on_event=on_event,
            permissions=permissions,
        )
        if auto_plan is not None:
            plan_md = auto_plan
    if on_event:
        on_event(
            "complete",
            {
                "session_id": folder.name,
                "path": str(folder),
                "cancelled": cancelled,
                "status": turn_status,
                "failed_agents": turn_summary["failed_agents"],
                "succeeded_agents": turn_summary["succeeded_agents"],
                "send_receipt": send_receipt_val,
                "inbox_pending": _sse_inbox_pending(folder),
                "turn_index": max(
                    0,
                    len((_read_run_meta(folder).get("turns") or [])) - 1,
                ),
                **_verified_loop_complete_payload(verified_result),
                **plan_workflow_complete_payload(folder),
            },
        )
    return messages, plan_md


def run_room(
    topic: str,
    *,
    agents: list[AgentId] | None = None,
    synthesize: bool = True,
    parallel_rounds: int = DEFAULT_AGENT_PARALLEL_ROUNDS,
    on_event: OnAgentEvent | None = None,
    sessions_base: Path | None = None,
    session_folder: Path | None = None,
    permissions: dict | None = None,
    review_mode: bool = False,
    consensus_mode: bool = False,
    efficiency_mode: bool = False,
    turn_profile: str | None = None,
    research_mode: bool = False,
) -> tuple[Path, list[ChatMessage], str]:
    """Full room flow: user message → parallel agents → optional plan synthesis."""
    from agent_lab.agent_permissions import normalize_agent_permissions

    permissions = normalize_agent_permissions(permissions)
    body = topic.strip()
    if session_folder and session_folder.is_dir():
        att = describe_attachments(session_folder)
        if att:
            body = f"{body}\n\n---\n\n{att}"
    messages: list[ChatMessage] = [ChatMessage(role="user", agent=None, content=body)]
    folder: Path | None = None
    if session_folder and session_folder.is_dir():
        folder = session_folder
        if (folder / "topic.txt").is_file():
            topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
        messages = load_session_messages(folder) + messages

    active_agents = [a for a in (agents or available_agents())]
    human_turn_index = _human_turn_count(messages) - 1
    mode = "plan" if synthesize else "discuss"
    review_advocate = (
        _review_advocate(active_agents, max(0, human_turn_index)) if review_mode and active_agents else None
    )
    plan_md, run_meta = _session_context(folder)
    _bind_session_to_run_meta(run_meta, folder)
    human_turn_num = max(1, _human_turn_count(messages))
    if folder is None and synthesize:
        boot = _bootstrap_session_folder_for_plan_workflow(
            topic,
            base=sessions_base,
            synthesize=synthesize,
        )
        if boot is not None:
            folder = boot
            plan_md, run_meta = _session_context(folder)
            _bind_session_to_run_meta(run_meta, folder)
    from agent_lab.room_team_orchestration import resolve_turn_lead

    resolve_turn_lead(
        run_meta,
        human_turn_num,
        [str(a) for a in active_agents],
        user_message=topic,
    )
    _set_active_turn_flags(
        run_meta,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
    from agent_lab.plan_workflow import (
        init_plan_workflow_on_plan_send,
        plan_workflow_skips_server_clarifier,
        should_enable_plan_workflow,
    )

    if folder is not None and should_enable_plan_workflow(synthesize=synthesize):
        init_plan_workflow_on_plan_send(folder)
        plan_md, run_meta = _session_context(folder)
        _bind_session_to_run_meta(run_meta, folder)
    if turn_profile:
        tp = (turn_profile or "analyze").strip().lower()
        run_meta["turn_profile"] = "analyze" if tp == "discuss" else tp
        if run_meta["turn_profile"] == "specialist":
            from agent_lab.room_agent_capabilities import ensure_specialist_capabilities

            if not run_meta.get("agent_capabilities_custom"):
                ensure_specialist_capabilities(run_meta)
            parallel_rounds = max(parallel_rounds, 2)
        from agent_lab.plan_workflow import apply_legacy_verified_turn_profile

        apply_legacy_verified_turn_profile(folder, run_meta, synthesize=synthesize)
    if research_mode or run_meta.get("turn_profile") == "specialist":
        run_meta["research_mode"] = True
    from agent_lab.session_clarifier import (
        build_clarifier_interview,
        interview_prompts,
        persist_clarifier_interview,
        sync_clarifier_answers_from_inbox,
    )

    is_new = folder is None or not (folder / "chat.jsonl").is_file()
    if folder is not None:
        sync_clarifier_answers_from_inbox(folder)
    skip_server_clarifier = plan_workflow_skips_server_clarifier(run_meta)
    clarifier_interview = None
    clarifier_questions: list[str] | None = None
    if not skip_server_clarifier:
        clarifier_interview = build_clarifier_interview(
            body,
            is_new_session=is_new,
            human_message_count=human_turn_num,
            plan_mode=synthesize,
        )
        clarifier_questions = interview_prompts(clarifier_interview)
        if clarifier_interview and folder is not None:
            persist_clarifier_interview(folder, clarifier_interview)
        if clarifier_questions and on_event:
            on_event(
                "clarifier_prompt",
                {"questions": clarifier_questions, "interview": clarifier_interview},
            )
    t0 = time.perf_counter()
    context_log: list[dict[str, Any]] = []
    _prepare_team_coordination_before_round(
        folder,
        run_meta,
        active_agents,
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
    )
    consensus_meta: dict[str, Any] | None = None
    replies: list[ChatMessage] = []
    cancelled = False
    delegate_replies = None
    if folder is not None:
        delegate_replies = _try_delegate_turn(
            body=body,
            topic=topic,
            messages=messages,
            run_meta=run_meta,
            folder=folder,
            permissions=permissions,
            on_event=on_event,
            clarifier_questions=clarifier_questions,
            human_turn_num=human_turn_num,
        )
    try:
        if clarifier_questions:
            replies = []
        elif delegate_replies is not None:
            replies = delegate_replies
            parallel_rounds = 1
        elif consensus_mode:
            replies, consensus_meta = run_consensus_agent_rounds(
                topic,
                messages,
                agents=agents,
                on_event=on_event,
                permissions=permissions,
                human_turn_index=max(0, human_turn_index),
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
            parallel_rounds = consensus_meta.get("rounds", 1) if consensus_meta else 1
            if consensus_meta is not None and run_meta.get("_turn_category"):
                consensus_meta.setdefault("category", run_meta["_turn_category"])
        else:
            replies = run_agent_rounds(
                topic,
                messages,
                agents=agents,
                parallel_rounds=parallel_rounds,
                on_event=on_event,
                permissions=permissions,
                review_mode=review_mode,
                human_turn_index=max(0, human_turn_index),
                plan_md=plan_md,
                run_meta=run_meta,
                context_log=context_log,
                efficiency_mode=efficiency_mode,
            )
    except RoomRunCancelled:
        cancelled = True
    if cancelled or is_cancelled():
        cancelled = True
        if on_event:
            on_event("run_cancelled", {"message": "답변 중지됨"})
    messages.extend(replies)

    plan_before = _read_plan_before(folder)
    plan_md = plan_before
    if folder is not None:
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
        if synthesize and scribe_applied and not plan_md:
            plan_md = "## Plan synthesis failed\n\nunknown error"
    else:
        scribe_applied = _should_scribe_plan_after_turn(synthesize=synthesize, cancelled=cancelled)
        if scribe_applied:
            plan_md = _apply_scribe_after_turn(
                topic=topic,
                messages=messages,
                run_meta=run_meta,
                plan_before=plan_before,
                mode=mode,
                scribe=True,
                user_plan_send=synthesize,
                cancelled=cancelled,
                on_event=on_event,
                session_folder=folder,
                plan_trigger="plan_turn" if synthesize else "auto_turn",
            )
            if synthesize and not plan_md:
                plan_md = "## Plan synthesis failed\n\nunknown error"
    plan_trigger = _plan_trigger_for_turn(synthesize=synthesize, scribe_applied=scribe_applied)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    turn_summary = _agent_turn_summary(replies)
    turn_status = _turn_status_from_replies(
        replies,
        cancelled=cancelled,
        consensus_meta=consensus_meta,
        consensus_mode=consensus_mode,
    )
    _emit_turn_terminal_status(
        status=turn_status,
        replies=replies,
        on_event=on_event,
        consensus_mode=consensus_mode,
    )
    from agent_lab.room_tasks import team_lead
    from agent_lab.room_team_orchestration import resolve_send_receipt, turn_leads_map
    from agent_lab.plan_workflow import is_plan_workflow_active, plan_workflow_complete_payload, plan_workflow_phase

    peer = _peer_metrics_for_messages(messages)
    pw_phase = plan_workflow_phase(run_meta) if is_plan_workflow_active(run_meta) else None
    send_receipt_val = resolve_send_receipt(
        mode=mode,
        synthesize=synthesize,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        plan_updated=bool(scribe_applied and not cancelled and plan_md and plan_md != plan_before),
        status=turn_status,
        plan_workflow_phase=pw_phase,
    )
    communicate_meta = _communicate_meta_for_turn(
        replies,
        context_log,
        parallel_rounds=parallel_rounds,
        review_mode=review_mode,
        consensus_mode=consensus_mode,
        turn_profile=turn_profile or str(run_meta.get("turn_profile") or ""),
        efficiency_mode=efficiency_mode,
    )
    turn_meta = _turn_snapshot(
        mode=mode,
        synthesize=synthesize,
        agents_used=active_agents,
        parallel_rounds=parallel_rounds,
        permissions=permissions,
        latency_ms=latency_ms,
        status=turn_status,
        review_mode=review_mode,
        review_advocate=review_advocate,
        context_log=context_log,
        consensus_mode=consensus_mode,
        consensus=consensus_meta,
        efficiency_mode=efficiency_mode,
        turn_state=_final_turn_state_dict(
            messages,
            run_meta=run_meta,
            active_agents=active_agents,
            consensus_meta=consensus_meta,
            plan_md=plan_md,
        ),
        turn_profile=turn_profile,
        turn_lead=team_lead(run_meta),
        turn_leads=turn_leads_map(run_meta),
        send_receipt=send_receipt_val,
        peer_message_count=int(peer.get("peer_message_count") or 0),
        agents_with_r2_reply=list(peer.get("agents_with_r2_reply") or []),
        failed_agents=turn_summary["failed_agents"],
        succeeded_agents=turn_summary["succeeded_agents"],
        last_delegate=run_meta.get("last_delegate"),
        plan_trigger=plan_trigger,
        communicate_meta=communicate_meta,
        category=run_meta.get("_turn_category"),
    )

    from agent_lab.goal_loop import (
        goal_auto_continue_enabled,
        maybe_check_session_goal_after_turn,
    )
    from agent_lab.plan_workflow import plan_workflow_skips_goal_check
    from agent_lab.verified_loop import normalize_verified_profile

    active_profile = turn_profile or run_meta.get("turn_profile")
    verified_result = _maybe_verified_loop_after_turn(
        folder,
        messages,
        active_profile,
        cancelled=cancelled,
    )
    verified_continue = None if cancelled else _verified_loop_continue_message(verified_result)

    if folder is None:
        folder = save_room_session(
            topic,
            messages,
            plan_md,
            base=sessions_base,
            agents_used=active_agents,
            turn_meta=turn_meta,
            clarifier_questions=clarifier_questions,
        )
        if should_enable_plan_workflow(synthesize=synthesize):
            init_plan_workflow_on_plan_send(folder)
    else:
        existing_meta: dict[str, Any] = {}
        if (folder / "meta.json").is_file():
            try:
                existing_meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        _write_session_files(
            folder,
            topic,
            messages,
            plan_md,
            agents_used=active_agents,
            merge_meta=existing_meta,
            turn_meta=turn_meta,
            run_meta_patch=_delegate_run_meta_patch(run_meta),
            clarifier_questions=clarifier_questions,
        )
    _finalize_durable_turn(folder, 1, turn_status)
    if verified_continue:
        auto_messages, auto_plan_md = continue_room_round(
            folder,
            verified_continue,
            agents=active_agents,
            synthesize=False,
            parallel_rounds=1,
            on_event=on_event,
            permissions=permissions,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=efficiency_mode,
            turn_profile=active_profile or "verified",
            research_mode=research_mode,
            _verified_loop_depth=1,
        )
        return folder, auto_messages, auto_plan_md

    goal_result = None
    if not normalize_verified_profile(active_profile) and not plan_workflow_skips_goal_check(run_meta):
        goal_result = maybe_check_session_goal_after_turn(folder, messages)
    goal_continue = _goal_auto_continue_message(goal_result)
    if goal_auto_continue_enabled() and goal_continue:
        auto_messages, auto_plan_md = continue_room_round(
            folder,
            goal_continue,
            agents=active_agents,
            synthesize=False,
            parallel_rounds=1,
            on_event=on_event,
            permissions=permissions,
            review_mode=False,
            consensus_mode=False,
            efficiency_mode=efficiency_mode,
            turn_profile="analyze",
            research_mode=research_mode,
            _goal_auto_continue_depth=1,
        )
        return folder, auto_messages, auto_plan_md
    auto_plan = maybe_auto_scribe_after_verified_loop(
        folder,
        verified_result=verified_result,
        cancelled=cancelled,
        on_event=on_event,
        permissions=permissions,
    )
    if auto_plan is not None:
        plan_md = auto_plan
    elif not normalize_verified_profile(active_profile):
        auto_plan = maybe_auto_scribe_after_consensus(
            folder,
            consensus_meta=consensus_meta,
            synthesize=synthesize,
            cancelled=cancelled,
            on_event=on_event,
            permissions=permissions,
        )
        if auto_plan is not None:
            plan_md = auto_plan
    if on_event:
        on_event(
            "complete",
            {
                "session_id": folder.name,
                "path": str(folder),
                "cancelled": cancelled,
                "status": turn_status,
                "failed_agents": turn_summary["failed_agents"],
                "succeeded_agents": turn_summary["succeeded_agents"],
                "send_receipt": send_receipt_val,
                "inbox_pending": _sse_inbox_pending(folder),
                "turn_index": max(
                    0,
                    len((_read_run_meta(folder).get("turns") or [])) - 1,
                ),
                **_verified_loop_complete_payload(verified_result),
                **plan_workflow_complete_payload(folder),
            },
        )
    return folder, messages, plan_md
