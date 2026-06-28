"""Weekly offline lane — card sync, WireUpDecision, runtime ingest (no proposal batch)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_lab.trading_mission.wireup_decision import (
    build_wireup_decision,
    mission_id_weekly,
    push_wireup_to_pipeline,
    write_wireup_artifacts,
)

_KST = timezone(timedelta(hours=9))
_DEFAULT_STATE = Path.home() / ".agent-lab" / "offline_lane_state.json"


def offline_state_path() -> Path:
    raw = (os.getenv("AGENT_LAB_OFFLINE_LANE_STATE") or "").strip()
    return Path(raw).expanduser() if raw else _DEFAULT_STATE


def _iso_week_key(when: datetime | None = None) -> str:
    dt = when or datetime.now(_KST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_KST)
    else:
        dt = dt.astimezone(_KST)
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def offline_lane_ran_this_week(state_path: Path | None = None) -> bool:
    path = state_path or offline_state_path()
    state = _load_state(path)
    return str(state.get("last_week") or "") == _iso_week_key()


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_plan_consensus(session_folder: Path, decision: dict[str, Any]) -> Path:
    plan_path = session_folder / "plan.md"
    active = decision.get("active_refs") if isinstance(decision.get("active_refs"), list) else []
    block = "\n".join(
        [
            "## 합의",
            f"- wireup_ready: {'true' if decision.get('wireup_ready') else 'false'}",
            "- ingest_ready: false",
            "- blocking_reason:",
            f"- active_strategies: {json.dumps(active, ensure_ascii=False)}",
            "- discuss_rounds_used: 0",
            "",
        ]
    )
    header = "# plan — Trading Mission offline lane\n\n"
    if plan_path.is_file():
        text = plan_path.read_text(encoding="utf-8")
        if "## 합의" not in text:
            plan_path.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
    else:
        plan_path.write_text(header + block, encoding="utf-8")
    return plan_path


def _seed_wisdom_note(session_folder: Path, decision: dict[str, Any]) -> Path | None:
    if os.getenv("AGENT_LAB_WISDOM_INDEX", "").strip().lower() not in ("1", "true", "yes", "on"):
        return None
    wisdom_dir = session_folder / "wisdom"
    wisdom_dir.mkdir(parents=True, exist_ok=True)
    mid = str(decision.get("mission_id") or mission_id_weekly())
    path = wisdom_dir / f"wireup-{mid}.md"
    active = decision.get("active_refs") or []
    blocked = decision.get("blocked_refs") or []
    path.write_text(
        "\n".join(
            [
                "# trading:wire_up",
                f"mission: {mid}",
                f"active_refs: {', '.join(active) if active else 'none'}",
                f"blocked_count: {len(blocked)}",
                "Use active_refs for proposal backtest_ref; FAIL refs remain blocked.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    try:
        from agent_lab.wisdom.index import build_wisdom_index

        build_wisdom_index(session_folder, force=True)
    except Exception:
        pass
    return path


def run_offline_lane(
    session_folder: Path,
    *,
    pipeline: Path | None = None,
    sync_cards: bool = True,
    push_runtime: bool = True,
    force: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    """Execute weekly offline lane into session artifacts + optional pipeline push."""
    folder = session_folder.expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "artifacts").mkdir(parents=True, exist_ok=True)

    state_path = offline_state_path()
    week_key = _iso_week_key()
    if not force and offline_lane_ran_this_week(state_path):
        return {
            "ok": True,
            "skipped": True,
            "reason": f"offline lane already ran for {week_key}",
            "session_folder": str(folder),
        }

    decision = build_wireup_decision(
        pipeline,
        mission_id=mission_id_weekly(),
        session_id=folder.name,
        sync_cards=sync_cards,
        notes=notes,
    )
    paths = write_wireup_artifacts(folder, decision)
    _write_plan_consensus(folder, decision)
    wisdom_path = _seed_wisdom_note(folder, decision)

    push_report: dict[str, Any] = {"skipped": True}
    if push_runtime:
        push_report = push_wireup_to_pipeline(decision, pipeline=pipeline)

    _save_state(
        state_path,
        {
            "last_week": week_key,
            "last_mission_id": decision.get("mission_id"),
            "last_session": folder.name,
            "last_run_at": decision.get("generated_at"),
            "active_refs": decision.get("active_refs"),
        },
    )

    return {
        "ok": bool(decision.get("wireup_ready")),
        "skipped": False,
        "mission_id": decision.get("mission_id"),
        "session_folder": str(folder),
        "wireup_ready": decision.get("wireup_ready"),
        "active_refs": decision.get("active_refs"),
        "blocked_refs_count": len(decision.get("blocked_refs") or []),
        "artifacts": {k: str(v) for k, v in paths.items()},
        "wisdom_note": str(wisdom_path) if wisdom_path else None,
        "runtime_push": push_report,
        "card_sync_written": (decision.get("card_sync") or {}).get("written"),
    }


def verify_offline_lane(session_folder: Path) -> dict[str, Any]:
    """Check wireup artifacts for weekly session."""
    folder = session_folder.expanduser().resolve()
    artifacts = folder / "artifacts"
    issues: list[str] = []

    wireup_path = artifacts / "wireup_decision.json"
    playbook_path = artifacts / "playbook.md"
    plan_path = folder / "plan.md"

    if not wireup_path.is_file():
        issues.append("missing_wireup_decision")
    if not playbook_path.is_file():
        issues.append("missing_playbook")
    if not plan_path.is_file():
        issues.append("missing_plan")

    decision: dict[str, Any] = {}
    if wireup_path.is_file():
        try:
            loaded = json.loads(wireup_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                decision = loaded
        except (OSError, json.JSONDecodeError):
            issues.append("invalid_wireup_decision")

    if decision and not decision.get("active_refs"):
        issues.append("no_active_refs")
    if decision and decision.get("schema") != "WireUpDecision/v1":
        issues.append("schema_mismatch")

    pb_text = ""
    if playbook_path.is_file():
        pb_text = playbook_path.read_text(encoding="utf-8", errors="replace")
        if "오늘 장중 행동" not in pb_text:
            issues.append("playbook_missing_intraday_section")

    return {
        "ok": not issues,
        "session_folder": str(folder),
        "issues": issues,
        "wireup_ready": bool(decision.get("wireup_ready")),
        "active_refs": decision.get("active_refs") or [],
    }
