#!/usr/bin/env python3
"""Pilot E2E across agent-lab session → native ingest → control plane console."""

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


def _bootstrap_env() -> None:
    from dotenv import load_dotenv

    from agent_lab.app_config import apply_config_env

    apply_config_env()
    for env_file in (ROOT / ".env", Path.home() / "Projects/agent-lab/.env"):
        if env_file.is_file():
            load_dotenv(env_file)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent-lab → native ingest → control plane pilot E2E")
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--legacy-ingest", action="store_true")
    parser.add_argument("--no-approve", action="store_true")
    parser.add_argument("--no-execute", action="store_true")
    args = parser.parse_args()

    _bootstrap_env()

    from agent_lab.trading_mission.ingest_bridge import ingest_proposal_batch
    from agent_lab.trading_mission.native_ingest import resolve_quant_pipeline_src

    src = resolve_quant_pipeline_src()
    if src is None:
        print("FAIL: quant_pipeline src not found", file=sys.stderr)
        return 1

    work = (args.work_dir or Path(tempfile.mkdtemp(prefix="agent-lab-pilot-e2e-"))).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    db_path = work / "control_plane.sqlite3"
    session = work / "pilot-session"

    os.environ["AGENTIC_TRADING_DB"] = str(db_path)
    os.environ["CONTROL_PLANE_DB"] = str(db_path)
    os.environ["AGENTIC_QUANT_PIPELINE_SRC"] = str(src)
    if not args.legacy_ingest:
        os.environ["AGENTIC_USE_NATIVE_INGEST"] = "1"

    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from quant_pipeline.agentic_trading.pilot_e2e import run_pilot_e2e, seed_pilot_session

    seed_pilot_session(session, mission_id="pilot-agent-lab")

    ingest_report = ingest_proposal_batch(session, db_path=db_path, force=True)
    print("ingest:", json.dumps(ingest_report, ensure_ascii=False, indent=2))
    if not ingest_report.get("ok"):
        return 1

    report = run_pilot_e2e(
        work,
        approve=not args.no_approve,
        execute=not args.no_execute,
        skip_seed=True,
        skip_ingest=True,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report.get("ok"):
        return 1

    print("\nPilot E2E OK")
    print(f"  db:      {db_path}")
    print(f"  session: {session}")
    print(f"  console: PYTHONPATH={src} python -m quant_pipeline.agentic_trading.server {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
