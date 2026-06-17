"""Offline communicate / hook KPIs from run.json (Hook · Communicate reform)."""

from __future__ import annotations

from typing import Any

from agent_lab.reply_policy import legacy_endorse_enabled


def communicate_counts(run_meta: dict[str, Any]) -> dict[str, Any]:
    turns = run_meta.get("turns") or []
    agent_replies = 0
    parse_errors = 0
    legacy_endorse = 0
    guidance_chars = 0
    strict_turns = 0
    acts_total: dict[str, int] = {}
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        meta = turn.get("communicate_meta") or {}
        if not isinstance(meta, dict):
            meta = {}
        agent_replies += int(meta.get("agent_reply_count") or 0)
        parse_errors += int(meta.get("envelope_parse_error_count") or 0)
        legacy_endorse += int(meta.get("legacy_endorse_count") or 0)
        guidance_chars += int(meta.get("guidance_chars") or 0)
        if meta.get("envelope_strict"):
            strict_turns += 1
        act_counts = meta.get("act_counts")
        if isinstance(act_counts, dict):
            for act, n in act_counts.items():
                try:
                    acts_total[str(act)] = acts_total.get(str(act), 0) + int(n)
                except (TypeError, ValueError):
                    continue

    hook_runs = [h for h in (run_meta.get("hook_runs") or []) if isinstance(h, dict)]
    hook_blocked = sum(1 for h in hook_runs if h.get("blocked"))
    hook_envelope_invalid = sum(1 for h in hook_runs if str(h.get("sub_reason") or "") == "envelope_invalid")

    ledger = [e for e in (run_meta.get("dispatch_ledger") or []) if isinstance(e, dict)]
    fanout_workers: list[int] = []
    for entry in ledger:
        agents = entry.get("agents")
        if isinstance(agents, list) and entry.get("status") == "done":
            fanout_workers.append(len(agents))

    return {
        "agent_replies": agent_replies,
        "envelope_parse_errors": parse_errors,
        "legacy_endorse_count": legacy_endorse if legacy_endorse_enabled() else 0,
        "guidance_chars_total": guidance_chars,
        "communicate_turns": len(turns),
        "envelope_strict_turns": strict_turns,
        "hook_runs": len(hook_runs),
        "hook_blocked": hook_blocked,
        "hook_envelope_invalid": hook_envelope_invalid,
        "acts_total": acts_total,
        "dispatch_count": len(ledger),
        "dispatch_fanout_avg": (sum(fanout_workers) / len(fanout_workers) if fanout_workers else None),
    }


def communicate_scores(counts: dict[str, Any]) -> dict[str, float | None]:
    replies = int(counts.get("agent_replies") or 0)
    parse_errors = int(counts.get("envelope_parse_errors") or 0)
    legacy_enabled = legacy_endorse_enabled()
    legacy = int(counts.get("legacy_endorse_count") or 0) if legacy_enabled else None
    guidance_turns = int(counts.get("communicate_turns") or 0)
    guidance_total = int(counts.get("guidance_chars_total") or 0)
    hook_runs = int(counts.get("hook_runs") or 0)
    hook_blocked = int(counts.get("hook_blocked") or 0)

    acts = counts.get("acts_total")
    acts = acts if isinstance(acts, dict) else {}
    challenge_like = int(acts.get("CHALLENGE") or 0) + int(acts.get("BLOCK") or 0)
    endorse = int(acts.get("ENDORSE") or 0)
    amend = int(acts.get("AMEND") or 0)

    def _rate(numerator: int | None, denominator: int) -> float | None:
        if numerator is None:
            return None
        return numerator / denominator if denominator else None

    return {
        "envelope_parse_success_rate": _rate(
            replies - parse_errors if replies else None,
            replies,
        ),
        "legacy_endorse_rate": _rate(legacy, replies),
        "median_guidance_chars_per_turn": (guidance_total / guidance_turns if guidance_turns else None),
        "hook_block_rate": _rate(hook_blocked, hook_runs),
        "challenge_rate": _rate(challenge_like, replies),
        "endorse_rate": _rate(endorse, replies),
        "amend_rate": _rate(amend, replies),
    }
