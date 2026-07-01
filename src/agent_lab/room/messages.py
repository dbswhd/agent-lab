"""Room message model, constants, and thread helpers."""

from __future__ import annotations

from agent_lab.room._typing import agent_label
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, cast

from agent_lab.context.bundle import ContextBundle
from agent_lab.agents.registry import AgentId
from agent_lab.agent.permissions import (
    apply_discuss_executor_policy,
    normalize_agent_permissions,
)
from agent_lab.session.guidance import (
    apply_discuss_workspace,
    resolve_session_workspace_binding,
)

MAX_AGENTS_PER_ROUND = 3
MAX_AGENT_PARALLEL_ROUNDS = 4  # per human message
DEFAULT_AGENT_PARALLEL_ROUNDS = 1  # discuss default; use 2+ for review / peer debate
RUN_SCHEMA_VERSION = 1
PLAN_FORMAT_VERSION = 1  # 지금 실행 + 실행 순서 sections
# Review round 2+: sequential pipeline (review → verify → execute; roster-filtered).
REVIEW_ROUND2_ORDER: tuple[AgentId, ...] = ("claude", "kimi_work", "codex", "cursor")

OnAgentEvent = Callable[[str, dict[str, Any]], None]
# event types: agent_start, agent_activity, agent_done, agent_error, turn_failed


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
    retry_of_turn: int | None = None  # set on a reply produced by partial-turn retry

    def to_dict(self) -> dict[str, Any]:
        from agent_lab.room.chat_channels import normalize_visibility

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
        if self.retry_of_turn is not None:
            d["retry_of_turn"] = self.retry_of_turn
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
            lines.append(f"{agent_label(m.agent)}:\n{m.content}\n")
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
        from agent_lab.room.team_orchestration import normalize_turn_profile

        if normalize_turn_profile(run_meta.get("turn_profile")) == "specialist":
            from agent_lab.room.agent_capabilities import specialist_round_agents

            ordered = specialist_round_agents([str(a) for a in agents], parallel_round)
            pool = {str(a).lower(): a for a in agents}
            return [pool[k] for k in ordered if k in pool]
    if review_mode and parallel_round >= 2:
        from agent_lab.room.roster_context import review_round2_order

        pool = {str(a).lower(): a for a in agents}
        return [pool[k] for k in review_round2_order([str(a) for a in agents]) if k in pool]
    if parallel_round == 1 and run_meta and not review_mode:
        from agent_lab.room.team_orchestration import team_r1_split

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
    from agent_lab.agent.permissions import permission_preamble
    from agent_lab.context.bundle import build_context_bundle

    bundle = build_context_bundle(
        topic,
        cast(Any, messages),
        agent,
        permission_lines=permission_preamble(permissions, agent, run_meta),
        parallel_round=parallel_round,
        review_mode=review_mode,
        review_advocate=review_advocate,
        plan_md=plan_md,
        run_meta=run_meta,
        permissions=permissions,
        all_messages=cast(Any, messages),
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
) -> ContextBundle:
    """ContextBundle for preview / debugging (payload + layer metadata)."""
    from agent_lab.agent.permissions import permission_preamble
    from agent_lab.context.bundle import ContextBundle, build_context_bundle

    return build_context_bundle(
        topic,
        cast(Any, messages),
        agent,
        permission_lines=permission_preamble(permissions, agent, run_meta),
        parallel_round=parallel_round,
        review_mode=review_mode,
        review_advocate=review_advocate,
        plan_md=plan_md,
        run_meta=run_meta,
        permissions=permissions,
        all_messages=cast(Any, messages),
        efficiency_mode=efficiency_mode,
        slim_context=slim_context,
        consensus_mode=consensus_mode,
    )


def _effective_room_permissions(
    permissions: dict | None,
    *,
    topic: str,
    plan_md: str,
    run_meta: dict[str, Any] | None,
) -> dict:
    """Permissions SSOT for Room turns — workspace binding only (no discuss overlay)."""
    binding = resolve_session_workspace_binding(
        permissions,
        topic=topic,
        plan_md=plan_md,
        run_meta=run_meta,
    )
    perms = normalize_agent_permissions(permissions)
    return apply_discuss_workspace(perms, binding)


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


def effective_agent_permissions(
    permissions: dict | None,
    *,
    topic: str,
    plan_md: str,
    run_meta: dict[str, Any] | None,
) -> dict:
    """Room invoke permissions — TurnPolicy ON uses SSOT; legacy uses discuss overlay."""
    from agent_lab.room.turn_policy import turn_policy_enabled

    if turn_policy_enabled():
        return _effective_room_permissions(
            permissions,
            topic=topic,
            plan_md=plan_md,
            run_meta=run_meta,
        )
    return _effective_discuss_permissions(
        permissions,
        topic=topic,
        plan_md=plan_md,
        run_meta=run_meta,
    )


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
