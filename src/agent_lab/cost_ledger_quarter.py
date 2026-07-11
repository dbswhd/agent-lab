"""F8 — quarterly cost ledger (cross-session USD rollup).

Session spend lives in ``run.json.cost_ledger``. This module maintains
``.agent-lab/cost_ledger_quarter.json`` under the project outcomes root and can
demote autonomy when the quarterly cap is exceeded.
"""

from __future__ import annotations

from agent_lab.time_utils import utc_now_iso_seconds as _now_iso, utc_now
from agent_lab.env_flags import is_truthy
from agent_lab.run.state import RunStateLike
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any



def current_quarter(now: datetime | None = None) -> str:
    when = now or utc_now()
    q = (when.month - 1) // 3 + 1
    return f"{when.year}-Q{q}"


def quarter_budget_usd() -> float | None:
    raw = (os.getenv("AGENT_LAB_QUARTER_BUDGET_USD") or "").strip()
    if not raw:
        return None
    try:
        limit = float(raw)
    except ValueError:
        return None
    return limit if limit > 0 else None


def quarter_warn_pct() -> float:
    raw = (os.getenv("AGENT_LAB_QUARTER_BUDGET_WARN_PCT") or "").strip()
    try:
        pct = float(raw)
    except ValueError:
        pct = 80.0
    return pct if 0 < pct <= 100 else 80.0


def demote_on_quarter_over_enabled() -> bool:
    """Default ON when a quarter budget is set; explicit 0 disables demotion."""
    raw = os.getenv("AGENT_LAB_QUARTER_BUDGET_DEMOTE")
    if not raw or not raw.strip():
        return quarter_budget_usd() is not None
    return is_truthy(raw)


def _outcomes_root() -> Path:
    from agent_lab.outcome_harvester import outcomes_path

    # outcomes_path → <root>/.agent-lab/outcomes.jsonl
    return outcomes_path().parent.parent


def quarter_ledger_path(root: Path | None = None) -> Path:
    base = root or _outcomes_root()
    return base / ".agent-lab" / "cost_ledger_quarter.json"


def _empty_quarter(quarter: str) -> dict[str, Any]:
    return {
        "quarter": quarter,
        "spent_usd": 0.0,
        "by_session": {},
        "updated_at": _now_iso(),
    }


def read_quarter_ledger(root: Path | None = None) -> dict[str, Any]:
    path = quarter_ledger_path(root)
    quarter = current_quarter()
    if not path.is_file():
        return _empty_quarter(quarter)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # ValueError covers JSONDecodeError + UnicodeDecodeError
        return _empty_quarter(quarter)
    if not isinstance(data, dict):
        return _empty_quarter(quarter)
    if str(data.get("quarter") or "") != quarter:
        return _empty_quarter(quarter)
    by_session = data.get("by_session")
    if not isinstance(by_session, dict):
        by_session = {}
    spent = float(data.get("spent_usd") or 0.0)
    return {
        "quarter": quarter,
        "spent_usd": round(spent, 6),
        "by_session": {str(k): float(v or 0.0) for k, v in by_session.items()},
        "updated_at": str(data.get("updated_at") or _now_iso()),
    }


def _write_quarter_ledger(payload: dict[str, Any], root: Path | None = None) -> Path:
    path = quarter_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def session_spent_usd(run_meta: RunStateLike | None) -> float:
    if not isinstance(run_meta, dict):
        return 0.0
    ledger = run_meta.get("cost_ledger")
    if not isinstance(ledger, dict):
        return 0.0
    cumulative = ledger.get("cumulative")
    if not isinstance(cumulative, dict):
        return 0.0
    return float(cumulative.get("usd") or 0.0)


def record_session_spend(
    session_id: str,
    spent_usd: float,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Upsert one session's spend into the current quarter rollup."""
    quarter = current_quarter()
    payload = read_quarter_ledger(root)
    if payload.get("quarter") != quarter:
        payload = _empty_quarter(quarter)
    by_session = dict(payload.get("by_session") or {})
    by_session[str(session_id)] = round(max(0.0, float(spent_usd)), 6)
    total = round(sum(float(v) for v in by_session.values()), 6)
    payload = {
        "quarter": quarter,
        "spent_usd": total,
        "by_session": by_session,
        "updated_at": _now_iso(),
    }
    _write_quarter_ledger(payload, root)
    return payload


def quarter_budget_status(root: Path | None = None) -> dict[str, Any]:
    payload = read_quarter_ledger(root)
    limit = quarter_budget_usd()
    spent = float(payload.get("spent_usd") or 0.0)
    warn_pct = quarter_warn_pct()
    over = limit is not None and spent >= limit
    warn = limit is not None and spent >= limit * (warn_pct / 100.0)
    return {
        "quarter": payload.get("quarter"),
        "limit_usd": limit,
        "spent_usd": round(spent, 6),
        "warn_pct": warn_pct,
        "over": over,
        "warn": warn,
        "session_count": len(payload.get("by_session") or {}),
        "updated_at": payload.get("updated_at"),
        "demote_enabled": demote_on_quarter_over_enabled(),
    }


def public_quarter_cost_payload(root: Path | None = None) -> dict[str, Any]:
    status = quarter_budget_status(root)
    return {
        "quarter": status["quarter"],
        "spent_usd": status["spent_usd"],
        "limit_usd": status["limit_usd"],
        "warn": status["warn"],
        "over": status["over"],
        "session_count": status["session_count"],
        "updated_at": status["updated_at"],
    }


def maybe_demote_autonomy_for_quarter_over(
    folder: Path,
    *,
    root: Path | None = None,
) -> dict[str, Any] | None:
    """When quarterly cap is exceeded, lower autonomy ceiling to L0 (F8)."""
    status = quarter_budget_status(root)
    if not status.get("over") or not status.get("demote_enabled"):
        return None
    from agent_lab.autonomy_ladder import (
        public_autonomy_payload,
        record_autonomy_transition,
        stored_autonomy_level,
    )
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(folder)
    ceiling = stored_autonomy_level(run)
    # Already at floor.
    if ceiling == "L0" or (ceiling is None and public_autonomy_payload(run).get("display_level") == "L0"):
        return public_autonomy_payload(run)
    return record_autonomy_transition(
        folder,
        to_level="L0",
        reason=f"quarter_budget_over:{status.get('quarter')}",
        trigger="demotion",
        from_level=ceiling or "L1",
    )


def sync_session_to_quarter(
    folder: Path,
    run_meta: RunStateLike | None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Record session spend and optionally demote autonomy."""
    spent = session_spent_usd(run_meta)
    payload = record_session_spend(folder.name, spent, root=root)
    maybe_demote_autonomy_for_quarter_over(folder, root=root)
    return payload
