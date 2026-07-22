"""Peer digest formatting for parallel/sequential room rounds."""

from __future__ import annotations

from agent_lab.room._typing import agent_label
from agent_lab.room.context._shared import MessageLike, env_bool


def collect_peer_messages(
    messages: list[MessageLike],
    agent: str,
    parallel_round: int,
) -> list[MessageLike]:
    """Messages shown in [이번 턴 · 동료 발화] for this agent and round."""
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    turn_msgs = messages[last_user + 1 :] if last_user >= 0 else messages
    same_round = [
        m
        for m in turn_msgs
        if m.role == "agent" and m.agent and m.agent != agent and (m.parallel_round or 1) == parallel_round
    ]
    if same_round:
        return same_round
    if parallel_round > 1:
        prev = parallel_round - 1
        return [
            m
            for m in turn_msgs
            if m.role == "agent" and m.agent and m.agent != agent and (m.parallel_round or 1) == prev
        ]
    return []


def dedupe_peer_from_recent(
    recent: list[MessageLike],
    peer_msgs: list[MessageLike],
    compact: bool | None = None,
) -> tuple[list[MessageLike], int]:
    """Drop agent lines from [최근 N턴] that already appear in [동료 발화]."""
    if not peer_msgs:
        return recent, 0
    if compact is None:
        compact = env_bool("AGENT_LAB_COMMS_COMPACT")
    if compact:
        return recent, 0
    peer_ids = {id(m) for m in peer_msgs}
    out: list[MessageLike] = []
    removed = 0
    for m in recent:
        if m.role == "agent" and id(m) in peer_ids:
            removed += 1
            continue
        out.append(m)
    return out, removed


def _format_peer_digest(m: MessageLike) -> str:
    """Compact blackboard entry for a peer reply."""
    body = (m.content or "").strip()
    excerpt = body[:140].replace("\n", " ")
    if len(body) > 140:
        excerpt = excerpt[:-1] + "…"
    envelope = getattr(m, "envelope", None) or {}
    act = str(envelope.get("act") or "").upper()
    if not act:
        first = body.splitlines()[0].upper() if body else ""
        for candidate in ("ENDORSE", "AMEND", "CHALLENGE", "PROPOSE", "BLOCK", "PASS", "MESSAGE", "NOTE"):
            if candidate in first:
                act = candidate
                break
    if not act:
        act = "SAY"
    refs = envelope.get("refs") or []
    ref_part = f" [refs: {', '.join(str(r) for r in refs)}]" if refs else ""
    round_n = m.parallel_round or 1
    header = f"L{round_n} {agent_label(m.agent)} {act}:"
    return f"{header} {excerpt}{ref_part}"


def format_peer_block(peer_msgs: list[MessageLike], compact: bool | None = None) -> str:
    if not peer_msgs:
        return ""
    if compact is None:
        compact = env_bool("AGENT_LAB_COMMS_COMPACT")
    lines = ["[이번 턴 · 동료 발화]"]
    for m in peer_msgs:
        body = (m.content or "").strip()
        if not body or not m.agent:
            continue
        if compact:
            lines.append(_format_peer_digest(m))
        else:
            lines.append(f"{agent_label(m.agent)}:\n{body}\n")
    return "\n".join(lines).strip()


def collect_r1_turn_replies(messages: list[MessageLike]) -> list[MessageLike]:
    """Agent round-1 replies in the current human turn (for R1.5 bridge)."""
    last_user = -1
    for i, m in enumerate(messages):
        if m.role == "user":
            last_user = i
    if last_user < 0:
        return []
    out: list[MessageLike] = []
    for m in messages[last_user + 1 :]:
        if m.role == "agent" and (m.parallel_round or 1) == 1:
            out.append(m)
    return out


def _r15_bridge_enabled() -> bool:
    return env_bool("AGENT_LAB_R15")


def build_turn_bridge_block(
    messages: list[MessageLike],
    *,
    parallel_round: int,
    max_chars: int = 400,
) -> str:
    """Optional R1 summary before round 2+ (AGENT_LAB_R15=1)."""
    if parallel_round < 2 or not _r15_bridge_enabled():
        return ""
    r1 = collect_r1_turn_replies(messages)
    if not r1:
        return ""
    lines: list[str] = []
    for m in r1:
        if not m.agent:
            continue
        first = (m.content or "").strip().split("\n", 1)[0][:120]
        if first:
            lines.append(f"- {agent_label(m.agent)}: {first}")
    if not lines:
        return ""
    body = "\n".join(lines)
    if len(body) > max_chars:
        body = body[: max_chars - 1].rsplit("\n", 1)[0] + "…"
    return f"[R1 요약 · bridge]\n{body}"


def build_peer_round_block(
    messages: list[MessageLike],
    agent: str,
    parallel_round: int,
) -> str:
    """Format [이번 턴 · 동료 발화] for one agent round (backward-compatible API)."""
    return format_peer_block(collect_peer_messages(messages, agent, parallel_round))
