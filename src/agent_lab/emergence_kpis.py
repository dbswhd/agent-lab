"""Emergence KPIs — hybrid plan provenance, challenge yield, AMEND chains (창발 측정)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_lab.plan.refs import REF_BLOCK_PATTERN, extract_ref_line_numbers
from agent_lab.room.objections import list_objections
from agent_lab.run.state import RunStateLike

CONFLICT_ACTS = frozenset({"CHALLENGE", "BLOCK"})


def load_chat_speakers(chat_path: Path) -> list[tuple[str, str | None]]:
    """(role, agent) per non-empty chat.jsonl line — same 1-based numbering as plan refs."""
    if not chat_path.is_file():
        return []
    rows: list[tuple[str, str | None]] = []
    for line in chat_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            rows.append(("", None))
            continue
        if not isinstance(obj, dict):
            rows.append(("", None))
            continue
        agent = obj.get("agent")
        rows.append((str(obj.get("role") or ""), str(agent) if agent else None))
    return rows


def hybrid_action_rate(folder: Path) -> tuple[float | None, dict[str, int]]:
    """Plan bullets whose refs span ≥2 distinct agents — the compositional emergence signal."""
    plan_path = folder / "plan.md"
    counts = {"ref_bullets": 0, "hybrid_bullets": 0, "unresolved_refs": 0}
    if not plan_path.is_file():
        return None, counts
    speakers = load_chat_speakers(folder / "chat.jsonl")
    for line in plan_path.read_text(encoding="utf-8").splitlines():
        if "(ref:" not in line.lower() or "(ref: 불명확)" in line:
            continue
        refs: list[int] = []
        for m in REF_BLOCK_PATTERN.finditer(line):
            refs.extend(extract_ref_line_numbers(m.group(1)))
        if not refs:
            continue
        agents: set[str] = set()
        for n in refs:
            if 1 <= n <= len(speakers):
                role, agent = speakers[n - 1]
                if role == "agent" and agent:
                    agents.add(agent)
            else:
                counts["unresolved_refs"] += 1
        if not agents:
            continue
        counts["ref_bullets"] += 1
        if len(agents) >= 2:
            counts["hybrid_bullets"] += 1
    if counts["ref_bullets"] == 0:
        return None, counts
    return counts["hybrid_bullets"] / counts["ref_bullets"], counts


def challenge_yield(run_meta: RunStateLike) -> tuple[float | None, dict[str, int]]:
    """CHALLENGE/BLOCK objections that were accepted — conflict that changed the output."""
    rows = [o for o in list_objections(run_meta) if o.get("act") in CONFLICT_ACTS]
    counts = {
        "total": len(rows),
        "resolved_accepted": sum(1 for o in rows if o.get("status") == "resolved_accepted"),
        "resolved_wontfix": sum(1 for o in rows if o.get("status") == "resolved_wontfix"),
        "open": sum(1 for o in rows if o.get("status") == "open"),
    }
    if counts["total"] == 0:
        return None, counts
    return counts["resolved_accepted"] / counts["total"], counts


def pure_challenge_yield_from_resolution(
    objection_resolution: dict[str, Any],
) -> tuple[float | None, dict[str, int]]:
    """CHALLENGE-only yield from ledger ``objection_resolution`` rollup."""
    challenge = (objection_resolution or {}).get("CHALLENGE") or {}
    accepted = int(challenge.get("accepted") or 0)
    wontfix = int(challenge.get("wontfix") or 0)
    open_n = int(challenge.get("open") or 0)
    total = accepted + wontfix + open_n
    counts = {
        "total": total,
        "resolved_accepted": accepted,
        "resolved_wontfix": wontfix,
        "open": open_n,
    }
    if total == 0:
        return None, counts
    return accepted / total, counts


def pure_challenge_yield(run_meta: RunStateLike) -> tuple[float | None, dict[str, int]]:
    """CHALLENGE-only objections that were accepted — excludes BLOCK from denominator."""
    rows = [o for o in list_objections(run_meta) if str(o.get("act") or "").strip().upper() == "CHALLENGE"]
    counts = {
        "total": len(rows),
        "resolved_accepted": sum(1 for o in rows if o.get("status") == "resolved_accepted"),
        "resolved_wontfix": sum(1 for o in rows if o.get("status") == "resolved_wontfix"),
        "open": sum(1 for o in rows if o.get("status") == "open"),
    }
    if counts["total"] == 0:
        return None, counts
    return counts["resolved_accepted"] / counts["total"], counts


def amend_chain_depth(messages: list[dict[str, Any]]) -> tuple[float | None, dict[str, int]]:
    """Max AMEND acts within one human turn — each AMEND re-anchors, so N AMENDs = chain of N.

    v1 heuristic; upgraded to real anchor lineage when anchor ids chain (P4).
    """
    amend_total = 0
    max_chain = 0
    current = 0
    agent_envelopes = 0
    for m in messages:
        if m.get("role") == "user":
            current = 0
            continue
        if m.get("role") != "agent":
            continue
        env = m.get("envelope")
        if not isinstance(env, dict):
            continue
        agent_envelopes += 1
        if str(env.get("act") or "").upper() == "AMEND":
            amend_total += 1
            current += 1
            max_chain = max(max_chain, current)
    counts = {"amend_total": amend_total, "max_chain_per_turn": max_chain}
    if agent_envelopes == 0:
        return None, counts
    return float(max_chain), counts


def act_distribution(messages: list[dict[str, Any]]) -> dict[str, int]:
    """Envelope act counts across the session — counts only, deliberately not scored."""
    dist: dict[str, int] = {}
    for m in messages:
        if m.get("role") != "agent":
            continue
        env = m.get("envelope")
        if not isinstance(env, dict):
            continue
        act = str(env.get("act") or "").upper()
        if act:
            dist[act] = dist.get(act, 0) + 1
    return dist


def anchor_chain_depth(run_meta: RunStateLike) -> tuple[float | None, dict[str, int]]:
    """P4 anchor 계보 — 턴별 재앵커(parent_id 체인) 최대 깊이. lineage 없으면 None."""
    max_depth = 0
    turns_with_lineage = 0
    for turn in run_meta.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        consensus = turn.get("consensus")
        if not isinstance(consensus, dict):
            continue
        lineage = consensus.get("anchor_lineage")
        if not isinstance(lineage, list) or not lineage:
            continue
        turns_with_lineage += 1
        max_depth = max(max_depth, len(lineage) - 1)
    counts = {"turns_with_lineage": turns_with_lineage, "max_chain": max_depth}
    if turns_with_lineage == 0:
        return None, counts
    return float(max_depth), counts


def recombination_kpis(
    run_meta: RunStateLike,
) -> tuple[float | None, dict[str, int]]:
    """P4 재조합 텔레메트리 — 합성 응답 중 refs가 타 에이전트 2명 이상인 비율."""
    replies = 0
    valid = 0
    rounds_run = 0
    skipped = 0
    for turn in run_meta.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        consensus = turn.get("consensus")
        if not isinstance(consensus, dict):
            continue
        recomb = consensus.get("recombination")
        if not isinstance(recomb, dict):
            continue
        if recomb.get("skipped"):
            skipped += 1
            continue
        rounds_run += 1
        replies += int(recomb.get("replies") or 0)
        valid += int(recomb.get("valid_syntheses") or 0)
    counts = {
        "rounds_run": rounds_run,
        "skipped": skipped,
        "replies": replies,
        "valid_syntheses": valid,
    }
    if replies == 0:
        return None, counts
    return valid / replies, counts


def routing_kpis(run_meta: RunStateLike) -> tuple[dict[str, float | None], dict[str, Any]]:
    """Topic-router telemetry — escalation_rate가 높으면 분류기가 과소평가 중."""
    distribution: dict[str, int] = {}
    auto_routed = 0
    escalated = 0
    quick_calls: list[int] = []
    standard_calls: list[int] = []
    for turn in run_meta.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        cat = turn.get("category")
        if not isinstance(cat, dict):
            continue
        value = str(cat.get("value") or "")
        if not value:
            continue
        distribution[value] = distribution.get(value, 0) + 1
        if cat.get("source") in ("heuristic", "profile"):
            auto_routed += 1
            if cat.get("escalated_from"):
                escalated += 1
        consensus = turn.get("consensus") or {}
        calls = consensus.get("calls") if isinstance(consensus, dict) else None
        if isinstance(calls, int):
            if value == "quick" and not cat.get("escalated_from"):
                quick_calls.append(calls)
            elif value == "standard":
                standard_calls.append(calls)
    counts: dict[str, Any] = {
        "distribution": distribution,
        "auto_routed": auto_routed,
        "escalated": escalated,
        "quick_turns_with_calls": len(quick_calls),
        "standard_turns_with_calls": len(standard_calls),
    }
    escalation_rate = escalated / auto_routed if auto_routed else None
    savings: float | None = None
    if quick_calls and standard_calls:
        savings = (sum(standard_calls) / len(standard_calls)) - (sum(quick_calls) / len(quick_calls))
    return {"escalation_rate": escalation_rate, "quick_call_savings": savings}, counts


def dispatch_fanout_rate(run_meta: RunStateLike) -> tuple[float | None, dict[str, int]]:
    """Share of dispatch ledger rows that used parallel_delegate (CMD-RDP)."""
    ledger = [e for e in (run_meta.get("dispatch_ledger") or []) if isinstance(e, dict)]
    counts = {"total": len(ledger), "parallel": 0, "single": 0}
    for entry in ledger:
        op = str(entry.get("op") or "")
        if op == "parallel_delegate":
            counts["parallel"] += 1
        elif op == "single_delegate":
            counts["single"] += 1
    if counts["total"] == 0:
        return None, counts
    return counts["parallel"] / counts["total"], counts


def emergence_kpis(
    folder: Path,
    run_meta: RunStateLike,
    messages: list[dict[str, Any]],
) -> tuple[dict[str, float | None], dict[str, Any]]:
    """Bundle emergence scores + counts for score_session."""
    hybrid_rate, hybrid_counts = hybrid_action_rate(folder)
    yield_rate, challenge_counts = challenge_yield(run_meta)
    pure_rate, pure_counts = pure_challenge_yield(run_meta)
    chain_depth, amend_counts = amend_chain_depth(messages)
    # P4: anchor 계보가 있으면 실제 재앵커 체인으로 업그레이드 (v1 휴리스틱 대체).
    lineage_depth, lineage_counts = anchor_chain_depth(run_meta)
    if lineage_depth is not None:
        chain_depth = lineage_depth
        amend_counts = {**amend_counts, **lineage_counts}
    recomb_rate, recomb_counts = recombination_kpis(run_meta)
    routing_scores, routing_counts = routing_kpis(run_meta)
    fanout_rate, dispatch_counts = dispatch_fanout_rate(run_meta)
    scores: dict[str, float | None] = {
        "hybrid_action_rate": hybrid_rate,
        "challenge_yield": yield_rate,
        "pure_challenge_yield": pure_rate,
        "amend_chain_depth_max": chain_depth,
        "recombination_validity_rate": recomb_rate,
        "dispatch_fanout_rate": fanout_rate,
        **routing_scores,
    }
    counts: dict[str, Any] = {
        "hybrid": hybrid_counts,
        "challenge": challenge_counts,
        "pure_challenge": pure_counts,
        "amend": amend_counts,
        "acts": act_distribution(messages),
        "recombination": recomb_counts,
        "routing": routing_counts,
        "dispatch": dispatch_counts,
    }
    return scores, counts
