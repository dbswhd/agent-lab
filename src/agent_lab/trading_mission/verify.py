"""Trading Mission artifact verification and goal oracle (P0)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_lab.plan.paths import read_trading_plan_md, trading_mission_plan_path
from agent_lab.trading_mission.artifact_cards import proposal_uses_fail_ref

_PLAYBOOK_HEADER = re.compile(r"오늘\s*장중\s*행동", re.IGNORECASE)


# Back-compat wrapper for ingest_bridge / plan_gate (positional snapshot arg)
def _proposal_has_fail_ref(
    proposal: dict[str, Any],
    snapshot: dict[str, Any] | None = None,
) -> bool:
    return proposal_uses_fail_ref(proposal, snapshot=snapshot)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def check_artifacts(session_folder: Path, *, check: str | None = None) -> dict[str, Any]:
    """Run one or all artifact checks. check: snapshot|cards|batch|playbook|goal|all"""
    mode = (check or "all").strip().lower()
    results: dict[str, Any] = {"ok": True, "checks": []}

    def record(name: str, ok: bool, detail: str = "") -> None:
        results["checks"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            results["ok"] = False

    artifacts = session_folder / "artifacts"
    snapshot = _load_json(artifacts / "market_snapshot.json") or {}

    if mode in ("all", "snapshot"):
        snap_path = artifacts / "market_snapshot.json"
        record("market_snapshot.json exists", snap_path.is_file())
        if snap_path.is_file():
            record(
                "snapshot has freshness or trade_allowed",
                "freshness" in snapshot or "trade_allowed" in snapshot,
            )
            record("snapshot has eligible_cards", "eligible_cards" in snapshot)

    if mode in ("all", "cards"):
        pipeline_root = str(snapshot.get("pipeline_root") or "").strip()
        cards_dir = Path(pipeline_root) / "data" / "agentic_trading" / "cards" if pipeline_root else None
        sync = snapshot.get("cards_sync") if isinstance(snapshot.get("cards_sync"), dict) else {}
        if mode == "cards" or pipeline_root:
            record("snapshot has pipeline_root", bool(pipeline_root))
            record("cards cache dir exists", bool(cards_dir and cards_dir.is_dir()))
            record(
                "strategy_card_index present",
                isinstance(snapshot.get("strategy_card_index"), list)
                and len(snapshot.get("strategy_card_index") or []) > 0,
                "run build-research-cards or preflight sync",
            )
            ineligible = snapshot.get("ineligible_refs") if isinstance(snapshot.get("ineligible_refs"), list) else []
            record(
                "ineligible_refs tracked",
                True,
                f"ineligible count={len(ineligible)}",
            )
            if sync.get("skipped"):
                record("cards sync skipped (fresh)", True, str(sync.get("reason") or ""))
            elif sync:
                record("cards sync ok", bool(sync.get("ok", True)), f"written={sync.get('written', 0)}")
        elif mode == "all":
            record("cards checks skipped", True, "no pipeline_root in snapshot")

    if mode in ("all", "batch"):
        batch = _load_json(artifacts / "proposal_batch.json") or {}
        record("proposal_batch.json exists", (artifacts / "proposal_batch.json").is_file())
        proposals = batch.get("proposals") if isinstance(batch.get("proposals"), list) else []
        fail_only = any(proposal_uses_fail_ref(p, snapshot=snapshot) for p in proposals if isinstance(p, dict))
        record("no FAIL-only proposals", not fail_only, "FAIL ref in batch")

    if mode in ("all", "playbook"):
        pb = artifacts / "playbook.md"
        record("playbook.md exists", pb.is_file())
        if pb.is_file():
            text = pb.read_text(encoding="utf-8", errors="replace")
            record("playbook has 장중 행동 section", bool(_PLAYBOOK_HEADER.search(text)))

    if mode in ("all", "goal"):
        goal = trading_mission_goal_ok(session_folder)
        record("trading mission goal", goal["ok"], goal.get("detail", ""))

    return results


def trading_mission_goal_ok(session_folder: Path) -> dict[str, Any]:
    """P0 goal oracle — artifact presence + FAIL ref guard."""
    artifacts = session_folder / "artifacts"
    missing: list[str] = []

    snap_path = artifacts / "market_snapshot.json"
    batch_path = artifacts / "proposal_batch.json"
    playbook_path = artifacts / "playbook.md"
    plan_path = trading_mission_plan_path(session_folder)
    legacy_plan = session_folder / "plan.md"

    for path in (snap_path, batch_path, playbook_path):
        if not path.is_file():
            missing.append(path.name)

    if not plan_path.is_file():
        if legacy_plan.is_file() and read_trading_plan_md(session_folder):
            pass
        else:
            missing.append(plan_path.name)

    if missing:
        return {"ok": False, "detail": "missing: " + ", ".join(missing)}

    snapshot = _load_json(snap_path) or {}
    batch = _load_json(batch_path) or {}
    proposals = batch.get("proposals") if isinstance(batch.get("proposals"), list) else []

    for proposal in proposals:
        if isinstance(proposal, dict) and proposal_uses_fail_ref(proposal, snapshot=snapshot):
            return {"ok": False, "detail": "FAIL backtest_ref in proposals"}

    plan_md = read_trading_plan_md(session_folder)
    if "ingest_ready" not in plan_md.lower():
        return {"ok": False, "detail": "trading plan missing ingest_ready in ## 합의"}

    playbook = playbook_path.read_text(encoding="utf-8", errors="replace")
    if not _PLAYBOOK_HEADER.search(playbook):
        return {"ok": False, "detail": "playbook missing 오늘 장중 행동"}

    return {"ok": True, "detail": "GOAL_OK"}
