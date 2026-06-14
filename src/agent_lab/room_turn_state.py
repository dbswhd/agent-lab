"""Lightweight per-turn blackboard (turn_state in run.json + agent payload)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from collections.abc import Sequence
from typing import Any, Protocol

from agent_lab.agent_envelope import envelope_act
from agent_lab.agents.registry import label
from agent_lab.room_consensus import pick_anchor
from agent_lab.room_context import extract_open_bullets

TURN_STATE_SCHEMA_VERSION = 1
_MAX_OPEN = 8
_MAX_DECISIONS = 6
_MAX_ACTS = 8

_PROPOSED_RE = re.compile(r"\[PROPOSED:\s*([^\]]+)\]", re.I)


class _MsgLike(Protocol):
    role: str
    agent: str | None
    content: str
    parallel_round: int | None
    envelope: dict[str, Any] | None


@dataclass
class TurnState:
    schema_version: int = TURN_STATE_SCHEMA_VERSION
    anchor: dict[str, Any] | None = None
    open_issues: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    pending_agents: list[str] = field(default_factory=list)
    consensus_status: str | None = None
    recent_acts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"schema_version": self.schema_version}
        if self.anchor:
            d["anchor"] = dict(self.anchor)
        if self.open_issues:
            d["open_issues"] = list(self.open_issues)
        if self.decisions:
            d["decisions"] = list(self.decisions)
        if self.pending_agents:
            d["pending_agents"] = list(self.pending_agents)
        if self.consensus_status:
            d["consensus_status"] = self.consensus_status
        if self.recent_acts:
            d["recent_acts"] = list(self.recent_acts)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TurnState | None:
        if not data or not isinstance(data, dict):
            return None
        return cls(
            schema_version=int(data.get("schema_version") or TURN_STATE_SCHEMA_VERSION),
            anchor=data.get("anchor"),
            open_issues=list(data.get("open_issues") or []),
            decisions=list(data.get("decisions") or []),
            pending_agents=list(data.get("pending_agents") or []),
            consensus_status=data.get("consensus_status"),
            recent_acts=list(data.get("recent_acts") or []),
        )


def _excerpt(text: str, *, max_len: int = 160) -> str:
    body = (text or "").strip()
    if not body:
        return ""
    first = body.splitlines()[0].strip()
    if len(first) >= 40:
        return first[:max_len]
    compact = " ".join(body.split())
    if len(compact) > max_len:
        return compact[: max_len - 1] + "…"
    return compact


def _proposed_from_turn(turn_messages: list[_MsgLike]) -> list[str]:
    found: list[str] = []
    for m in turn_messages:
        if m.role != "agent":
            continue
        for match in _PROPOSED_RE.finditer(m.content or ""):
            item = match.group(1).strip()
            if item and item not in found:
                found.append(item[:200])
    return found[:_MAX_OPEN]


def _recent_acts_from_turn(
    turn_messages: list[_MsgLike],
    *,
    line_base: int,
) -> list[dict[str, Any]]:
    acts: list[dict[str, Any]] = []
    for i, m in enumerate(turn_messages):
        if m.role != "agent" or not m.agent:
            continue
        act = envelope_act(m.envelope)
        if not act:
            continue
        ref = f"L{line_base + i}"
        entry: dict[str, Any] = {
            "agent": m.agent,
            "act": act,
            "ref": ref,
        }
        refs = (m.envelope or {}).get("refs") if m.envelope else None
        if refs:
            entry["refs"] = list(refs)
        acts.append(entry)
    return acts[-_MAX_ACTS:]


def derive_turn_state(
    turn_messages: list[_MsgLike],
    *,
    line_base: int = 1,
    active_agents: list[str] | None = None,
    consensus: dict[str, Any] | None = None,
    plan_md: str = "",
    pending_agents: list[str] | None = None,
) -> TurnState:
    """Build blackboard snapshot from current human turn (+ optional consensus meta)."""
    agents = active_agents or []
    anchor_dict: dict[str, Any] | None = None

    if consensus and consensus.get("anchor"):
        a = consensus["anchor"]
        anchor_dict = {
            "agent": a.get("agent"),
            "excerpt": a.get("excerpt", ""),
            "parallel_round": a.get("parallel_round"),
        }
        if consensus.get("status") == "reached":
            anchor_dict["ref"] = _anchor_ref(turn_messages, line_base, anchor_dict)
    elif agents:
        anchor = pick_anchor(turn_messages, agents)  # type: ignore[arg-type]
        if anchor:
            anchor_dict = {
                **anchor.to_dict(),
                "ref": _anchor_ref(turn_messages, line_base, anchor.to_dict()),
            }

    open_issues = _proposed_from_turn(turn_messages)
    plan_open = extract_open_bullets(plan_md)[:4]
    for item in plan_open:
        if item not in open_issues and len(open_issues) < _MAX_OPEN:
            open_issues.append(item[:200])

    decisions: list[str] = []
    status = consensus.get("status") if consensus else None
    if status == "reached" and anchor_dict:
        excerpt = str(anchor_dict.get("excerpt", ""))[:120]
        who = label(str(anchor_dict.get("agent", "")))
        ref = anchor_dict.get("ref", "")
        line = f"합의: {who} 제안 채택 — 「{excerpt}」"
        if ref:
            line += f" ({ref})"
        decisions.append(line)
        for agent_id in consensus.get("agents_consented") or []:
            decisions.append(f"{label(str(agent_id))} ENDORSE")
        decisions = decisions[:_MAX_DECISIONS]

    pending = list(pending_agents or [])
    if not pending and consensus and status != "reached":
        pending = list(consensus.get("pending_agents") or [])

    return TurnState(
        anchor=anchor_dict,
        open_issues=open_issues[:_MAX_OPEN],
        decisions=decisions,
        pending_agents=pending,
        consensus_status=status,
        recent_acts=_recent_acts_from_turn(turn_messages, line_base=line_base),
    )


def _anchor_ref(
    turn_messages: list[_MsgLike],
    line_base: int,
    anchor: dict[str, Any],
) -> str:
    agent = anchor.get("agent")
    pr = anchor.get("parallel_round")
    excerpt = str(anchor.get("excerpt", ""))[:80]
    for i, m in enumerate(turn_messages):
        if m.role != "agent" or m.agent != agent:
            continue
        if pr is not None and m.parallel_round != pr:
            continue
        if excerpt and excerpt not in (m.content or "") and _excerpt(m.content)[:40] not in excerpt:
            continue
        return f"chat.jsonl#L{line_base + i}"
    return ""


def render_turn_state_block(state: dict[str, Any] | TurnState | None) -> str:
    """Compact blackboard layer for agent payloads."""
    if state is None:
        return ""
    ts = state if isinstance(state, TurnState) else TurnState.from_dict(state)
    if ts is None:
        return ""
    lines = ["[턴 blackboard — structured turn state]"]
    if ts.anchor:
        a = ts.anchor
        who = label(str(a.get("agent", "")))
        ex = str(a.get("excerpt", ""))[:140]
        pr = a.get("parallel_round", "?")
        ref = a.get("ref", "")
        lines.append(f"앵커: {who} R{pr} — 「{ex}」" + (f" ({ref})" if ref else ""))
    if ts.open_issues:
        lines.append("미결 / PROPOSED:")
        for item in ts.open_issues[:5]:
            lines.append(f"- {item}")
    if ts.decisions:
        lines.append("결정:")
        for item in ts.decisions[:4]:
            lines.append(f"- {item}")
    if ts.pending_agents:
        names = ", ".join(label(a) for a in ts.pending_agents)
        lines.append(f"합의 대기: {names}")
    if ts.consensus_status:
        lines.append(f"consensus: {ts.consensus_status}")
    if ts.recent_acts:
        act_bits = [
            f"{label(str(x.get('agent', '')))} {x.get('act')} {x.get('ref', '')}".strip() for x in ts.recent_acts[-4:]
        ]
        lines.append("최근 act: " + " | ".join(act_bits))
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def current_turn_slice(
    all_messages: Sequence[_MsgLike],
) -> tuple[list[_MsgLike], int]:
    """Return (messages from latest Human through agents, 1-based line of turn[0])."""
    last_user = -1
    for i, m in enumerate(all_messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return all_messages, 1
    return all_messages[last_user:], last_user + 1


def peer_turn_metrics(turn_messages: list[_MsgLike]) -> dict[str, Any]:
    """R2 peer channel stats for turn diagnostics (D10)."""
    peer_count = 0
    agents_r2: set[str] = set()
    for m in turn_messages:
        if m.role != "agent":
            continue
        pr = m.parallel_round or 1
        if pr < 2:
            continue
        peer_count += 1
        if m.agent:
            agents_r2.add(str(m.agent).strip().lower())
    return {
        "peer_message_count": peer_count,
        "agents_with_r2_reply": sorted(agents_r2),
    }


def sync_run_meta_turn_state(
    run_meta: dict[str, Any] | None,
    all_messages: Sequence[_MsgLike],
    *,
    active_agents: Sequence[str] | None = None,
    consensus: dict[str, Any] | None = None,
    plan_md: str = "",
    pending_agents: list[str] | None = None,
) -> TurnState | None:
    if run_meta is None:
        return None
    turn_msgs, line_base = current_turn_slice(all_messages)
    state = derive_turn_state(
        turn_msgs,
        line_base=line_base,
        active_agents=active_agents,
        consensus=consensus,
        plan_md=plan_md,
        pending_agents=pending_agents,
    )
    run_meta["turn_state"] = state.to_dict()
    return state
