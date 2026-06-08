"""Offline communicate / hook KPIs from run.json (Hook · Communicate reform)."""

from __future__ import annotations

from typing import Any

from agent_lab.reply_policy import legacy_endorse_enabled


def communicate_counts(run_meta: dict[str, Any]) -> dict[str, int]:
    turns = run_meta.get("turns") or []
    agent_replies = 0
    parse_errors = 0
    legacy_endorse = 0
    guidance_chars = 0
    strict_turns = 0
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

    hook_runs = [h for h in (run_meta.get("hook_runs") or []) if isinstance(h, dict)]
    hook_blocked = sum(1 for h in hook_runs if h.get("blocked"))
    hook_envelope_invalid = sum(
        1 for h in hook_runs if str(h.get("sub_reason") or "") == "envelope_invalid"
    )

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
    }


def communicate_scores(counts: dict[str, int]) -> dict[str, float | None]:
    replies = int(counts.get("agent_replies") or 0)
    parse_errors = int(counts.get("envelope_parse_errors") or 0)
    legacy = int(counts.get("legacy_endorse_count") or 0)
    guidance_turns = int(counts.get("communicate_turns") or 0)
    guidance_total = int(counts.get("guidance_chars_total") or 0)
    hook_runs = int(counts.get("hook_runs") or 0)
    hook_blocked = int(counts.get("hook_blocked") or 0)

    return {
        "envelope_parse_success_rate": (
            (replies - parse_errors) / replies if replies else None
        ),
        "legacy_endorse_rate": (legacy / replies if replies else None),
        "median_guidance_chars_per_turn": (
            guidance_total / guidance_turns if guidance_turns else None
        ),
        "hook_block_rate": (hook_blocked / hook_runs if hook_runs else None),
    }
