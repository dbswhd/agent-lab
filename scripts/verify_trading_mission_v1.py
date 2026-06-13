#!/usr/bin/env python3
"""Verify Trading Mission v1 operational checklist (plan §7.10)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bootstrap() -> None:
    from dotenv import load_dotenv

    from agent_lab.app_config import apply_config_env

    apply_config_env()
    for env_file in (ROOT / ".env", Path.home() / "Projects/agent-lab/.env"):
        if env_file.is_file():
            load_dotenv(env_file)


def _run_pilot(work: Path) -> dict:
    from agent_lab.trading_mission.native_ingest import resolve_quant_pipeline_src

    src = resolve_quant_pipeline_src()
    if src is None:
        return {"ok": False, "reason": "quant_pipeline src not found"}
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from quant_pipeline.agentic_trading.pilot_e2e import run_pilot_e2e

    return run_pilot_e2e(work / "pilot-work", approve=False, execute=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Mission v1 ops checklist")
    parser.add_argument("--pass-session", type=Path, default=None, help="PASS premarket session folder")
    parser.add_argument("--blocked-session", type=Path, default=None)
    parser.add_argument("--fail-session", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=None, help="Control plane SQLite")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Run built-in PASS/blocked/FAIL fixtures + pilot ingest",
    )
    parser.add_argument("--pilot", action="store_true", help="Also run quant_pipeline pilot_e2e")
    args = parser.parse_args()

    _bootstrap()

    from agent_lab.trading_mission.v1_ops import (
        build_blocked_fixture,
        build_fail_ref_fixture,
        run_v1_checklist,
    )

    work = Path(tempfile.mkdtemp(prefix="v1-ops-")) if args.synthetic else None
    pass_session = args.pass_session
    blocked_session = args.blocked_session
    fail_session = args.fail_session
    db_path = args.db

    if args.synthetic and work is not None:
        fail_session = build_fail_ref_fixture(work)
        blocked_session = build_blocked_fixture(work)
        if args.pilot:
            pilot_report = _run_pilot(work / "pilot-work")
            if not pilot_report.get("ok"):
                print(json.dumps({"ok": False, "stage": "pilot", "pilot": pilot_report}, indent=2))
                return 1
            db_path = Path(pilot_report["db_path"])
            pass_session = Path(pilot_report["session_folder"])
        else:
            from agent_lab.trading_mission.native_ingest import resolve_quant_pipeline_src
            from quant_pipeline.agentic_trading.pilot_e2e import seed_pilot_session

            src = resolve_quant_pipeline_src()
            if src and str(src) not in sys.path:
                sys.path.insert(0, str(src))
            pass_session = work / "pass-session"
            seed_pilot_session(pass_session, mission_id="v1-ops-pass")
            db_path = work / "control_plane.sqlite3"
            os.environ["AGENTIC_USE_NATIVE_INGEST"] = "1"
            os.environ["AGENTIC_TRADING_DB"] = str(db_path)
            from agent_lab.trading_mission.ingest_bridge import ingest_proposal_batch

            ingest = ingest_proposal_batch(pass_session, db_path=db_path, force=True)
            if not ingest.get("ok"):
                print(json.dumps({"ok": False, "stage": "ingest", "ingest": ingest}, indent=2))
                return 1

    report = run_v1_checklist(
        pass_session=pass_session,
        blocked_session=blocked_session,
        fail_session=fail_session,
        db_path=db_path,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("ok"):
        print("\nv1 ops checklist: PASS")
    else:
        print("\nv1 ops checklist: FAIL", file=sys.stderr)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
