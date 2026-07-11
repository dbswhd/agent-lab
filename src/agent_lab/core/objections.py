"""Objection registry read helpers — run.json snapshot access (F12, stdlib only)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

RUN_OBJECTIONS_KEY = "objections"
HARVEST_ACTS = frozenset({"BLOCK", "CHALLENGE"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_objection_id() -> str:
    return f"obj-{uuid.uuid4().hex[:10]}"


def normalize_objection(raw: dict[str, Any]) -> dict[str, Any]:
    oid = str(raw.get("id") or _new_objection_id()).strip() or _new_objection_id()
    status = str(raw.get("status") or "open").strip().lower()
    if status not in ("open", "resolved_accepted", "resolved_wontfix"):
        status = "open"
    from_agent = str(raw.get("from") or "").strip().lower()
    act = str(raw.get("act") or "BLOCK").strip().upper()
    if act not in HARVEST_ACTS:
        act = "BLOCK"
    out: dict[str, Any] = {
        "id": oid,
        "from": from_agent,
        "act": act,
        "body": str(raw.get("body") or "").strip()[:4000],
        "status": status,
        "turn": int(raw.get("turn") or 0),
        "ts": str(raw.get("ts") or _now()),
    }
    if raw.get("target_ref"):
        out["target_ref"] = str(raw["target_ref"]).strip()[:120]
    if raw.get("task_id"):
        out["task_id"] = str(raw["task_id"]).strip()[:80]
    if raw.get("plan_action_index") is not None:
        try:
            out["plan_action_index"] = int(raw["plan_action_index"])
        except (TypeError, ValueError):
            pass
    if raw.get("plan_action_kind"):
        kind = str(raw["plan_action_kind"]).strip().lower()
        if kind in ("now", "roadmap", "legacy"):
            out["plan_action_kind"] = kind
    mode = str(raw.get("mode") or "plan").strip().lower()
    out["mode"] = mode if mode in ("plan", "discuss", "verified") else "plan"
    if raw.get("resolution"):
        out["resolution"] = str(raw["resolution"]).strip()[:80]
    if raw.get("resolved_at"):
        out["resolved_at"] = str(raw["resolved_at"])
    if raw.get("resolved_by"):
        out["resolved_by"] = str(raw["resolved_by"]).strip()[:40]
    if raw.get("resolve_note"):
        out["resolve_note"] = str(raw["resolve_note"]).strip()[:500]
    return out


def list_objections(run_meta: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not run_meta:
        return []
    raw = run_meta.get(RUN_OBJECTIONS_KEY)
    if not isinstance(raw, list):
        return []
    return [normalize_objection(o) for o in raw if isinstance(o, dict)]
