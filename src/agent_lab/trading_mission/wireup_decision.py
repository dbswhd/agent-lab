"""WireUpDecision — weekly PASS strategy selection for runtime ingest."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_lab.pipeline_research_read import (
    default_cards_dir,
    list_wireup_candidates,
    load_all_cached_cards,
    resolve_pipeline_root,
    sync_research_cards,
)
from agent_lab.quant_utility_validation import detect_pipeline_root

_KST = timezone(timedelta(hours=9))


def _now_kst_iso() -> str:
    return datetime.now(_KST).isoformat()


def _active_cap() -> int:
    raw = (os.getenv("AGENT_LAB_OFFLINE_ACTIVE_CAP") or "8").strip()
    try:
        return max(1, min(int(raw), 30))
    except ValueError:
        return 8


def _watch_cap() -> int:
    raw = (os.getenv("AGENT_LAB_OFFLINE_WATCH_CAP") or "12").strip()
    try:
        return max(0, min(int(raw), 40))
    except ValueError:
        return 12


def mission_id_weekly(date_kst: datetime | None = None) -> str:
    when = date_kst or datetime.now(_KST)
    return f"{when.strftime('%Y-%m-%d')}-weekly"


def build_wireup_decision(
    pipeline: Path | None = None,
    *,
    mission_id: str | None = None,
    session_id: str | None = None,
    sync_cards: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    """Build WireUpDecision from cached PASS/FAIL cards (optional full card sync)."""
    root = pipeline or detect_pipeline_root() or resolve_pipeline_root()
    root = root.resolve()

    sync_report: dict[str, Any] = {"skipped": True, "reason": "sync_cards=false"}
    if sync_cards:
        sync_report = sync_research_cards(root, include_ineligible=True)
        sync_report["skipped"] = False

    listed = list_wireup_candidates(pipeline=root, limit=50)
    cards = listed.get("cards") if isinstance(listed.get("cards"), list) else []
    active_cap = _active_cap()
    watch_cap = _watch_cap()

    active_refs: list[str] = []
    watch_refs: list[str] = []
    for idx, card in enumerate(cards):
        if not isinstance(card, dict):
            continue
        ref = str(card.get("ref") or "").strip()
        if not ref:
            continue
        if len(active_refs) < active_cap:
            active_refs.append(ref)
        elif len(watch_refs) < watch_cap:
            watch_refs.append(ref)

    all_cards = load_all_cached_cards(root)
    blocked_refs = sorted(
        {
            str(c.get("ref") or "").strip()
            for c in all_cards
            if isinstance(c, dict) and c.get("ref") and not c.get("eligible_for_proposal")
        }
    )

    mid = mission_id or mission_id_weekly()
    wireup_ready = bool(sync_report.get("ok", True)) and bool(active_refs)

    return {
        "schema": "WireUpDecision/v1",
        "mission_id": mid,
        "session_id": session_id or "",
        "generated_at": _now_kst_iso(),
        "pipeline_root": str(root),
        "wireup_ready": wireup_ready,
        "active_refs": active_refs,
        "watch_refs": watch_refs,
        "deprecated_refs": [],
        "blocked_refs": blocked_refs,
        "candidates_reviewed": int(listed.get("count") or len(cards)),
        "card_sync": sync_report,
        "cards_dir": str(default_cards_dir(root)),
        "notes": notes.strip(),
    }


def render_playbook_wireup_section(decision: dict[str, Any]) -> str:
    """Markdown block for pipeline/session playbook (weekly wire-up)."""
    active = decision.get("active_refs") if isinstance(decision.get("active_refs"), list) else []
    watch = decision.get("watch_refs") if isinstance(decision.get("watch_refs"), list) else []
    blocked = decision.get("blocked_refs") if isinstance(decision.get("blocked_refs"), list) else []
    mid = str(decision.get("mission_id") or "weekly")
    lines = [
        "# 주간 wire-up (offline lane)",
        "",
        f"- mission_id: `{mid}`",
        f"- generated_at: {decision.get('generated_at')}",
        f"- wireup_ready: {decision.get('wireup_ready')}",
        "",
        "## Active strategies (proposal-eligible)",
    ]
    if active:
        lines.extend(f"- `{ref}`" for ref in active)
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Watch list")
    if watch:
        lines.extend(f"- `{ref}`" for ref in watch[:12])
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Blocked (FAIL / ineligible)")
    if blocked:
        lines.extend(f"- `{ref}`" for ref in blocked[:20])
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## 오늘 장중 행동")
    lines.append("")
    lines.append("- Use **active_refs** only for new proposals; Human approve in console.")
    lines.append("- Do not propose blocked_refs; watch_refs need extra review.")
    if decision.get("notes"):
        lines.append(f"- Lab notes: {decision['notes']}")
    lines.append("")
    return "\n".join(lines)


def write_wireup_artifacts(
    session_folder: Path,
    decision: dict[str, Any],
) -> dict[str, Path]:
    """Persist wireup_decision.json + playbook.md under session artifacts."""
    artifacts = session_folder / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    decision_path = artifacts / "wireup_decision.json"
    playbook_path = artifacts / "playbook.md"
    decision_path.write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    playbook_path.write_text(render_playbook_wireup_section(decision), encoding="utf-8")
    return {"wireup_decision": decision_path, "playbook": playbook_path}


def push_wireup_to_pipeline(
    decision: dict[str, Any],
    *,
    pipeline: Path | None = None,
) -> dict[str, Any]:
    """Copy WireUpDecision + playbook into pipeline data/agentic for runtime MCP."""
    root = pipeline or Path(str(decision.get("pipeline_root") or "")).expanduser()
    if not root.is_dir():
        root = resolve_pipeline_root()
    agentic = root / "data" / "agentic"
    agentic.mkdir(parents=True, exist_ok=True)

    wireup_path = agentic / "wireup_decision.json"
    playbook_path = agentic / "playbook.md"
    wireup_path.write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    playbook_path.write_text(render_playbook_wireup_section(decision), encoding="utf-8")

    return {
        "ok": True,
        "pipeline_root": str(root),
        "wireup_decision": str(wireup_path),
        "playbook": str(playbook_path),
    }
