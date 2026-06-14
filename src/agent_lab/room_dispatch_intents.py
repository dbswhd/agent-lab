"""Pending dispatch intents from envelope MESSAGE + dispatch field (CMD-RDP Phase 3)."""

from __future__ import annotations

from typing import Any


def harvest_dispatch_intents_from_turn(
    run_meta: dict[str, Any],
    messages: list[Any],
    *,
    human_turn: int,
    issuer_agent: str | None = None,
) -> list[dict[str, Any]]:
    """Collect pending scoped-work intents; execution requires Human dispatch marker."""
    from agent_lab.agent_envelope import envelope_dispatch

    harvested: list[dict[str, Any]] = []
    for msg in messages:
        if getattr(msg, "role", None) != "agent":
            continue
        env = getattr(msg, "envelope", None)
        if not isinstance(env, dict):
            continue
        dispatch = envelope_dispatch(env)
        if not dispatch:
            continue
        to_agent = str(env.get("to") or "").strip().lower()
        prompt = str(dispatch.get("prompt") or env.get("message") or "").strip()
        if not to_agent or len(prompt) < 4:
            continue
        entry = {
            "id": f"intent-{human_turn}-{len(harvested) + 1}",
            "status": "pending",
            "issuer": issuer_agent or getattr(msg, "agent", None),
            "to": to_agent,
            "op": str(dispatch.get("op") or "scoped"),
            "prompt": prompt[:2000],
            "human_turn": human_turn,
        }
        harvested.append(entry)
    if not harvested:
        return []
    existing = list(run_meta.get("dispatch_intents") or [])
    existing.extend(harvested)
    run_meta["dispatch_intents"] = existing[-50:]
    return harvested


def pending_dispatch_intents(run_meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not run_meta:
        return []
    rows = run_meta.get("dispatch_intents") or []
    return [r for r in rows if isinstance(r, dict) and r.get("status") == "pending"]


def build_dispatch_intent_block(run_meta: dict[str, Any] | None, agent: str) -> str:
    """Context for turn lead — pending intents targeting this agent or issued by lead."""
    pending = pending_dispatch_intents(run_meta)
    if not pending:
        return ""
    aid = str(agent or "").strip().lower()
    lead = str((run_meta or {}).get("team_lead") or "").strip().lower()
    lines: list[str] = ["[dispatch intents · pending]"]
    for row in pending[-5:]:
        to_a = str(row.get("to") or "")
        if aid != lead and aid != to_a:
            continue
        lines.append(f"- {row.get('id')}: {row.get('issuer')} → {to_a}: {(row.get('prompt') or '')[:120]}")
    if len(lines) == 1:
        return ""
    lines.append("Human `DELEGATE`/`DISPATCH` 또는 리드 GO 후에만 실행됩니다.")
    return "\n".join(lines)
