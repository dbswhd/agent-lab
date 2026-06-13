#!/usr/bin/env python3
"""Weekly offline lane: card sync → WireUpDecision → pipeline runtime ingest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_KST = timezone(timedelta(hours=9))


def _bootstrap_env() -> None:
    from dotenv import load_dotenv

    from agent_lab.app_config import apply_config_env

    apply_config_env()
    home = Path.home()
    for env_file in (
        Path(os.getenv("DOTENV_PATH", "")),
        ROOT / ".env",
        home / "Projects/agent-lab/.env",
        home / ".agent-lab/.env",
    ):
        if env_file.is_file():
            load_dotenv(env_file)


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Mission weekly offline lane")
    parser.add_argument(
        "--session",
        type=Path,
        default=None,
        help="Session folder (default: sessions/YYYY-MM-DD-weekly-wireup)",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip card rebuild from research results",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Do not copy wireup/playbook to pipeline data/agentic",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if offline lane already ran this ISO week",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional Lab notes stored on WireUpDecision",
    )
    args = parser.parse_args()

    _bootstrap_env()

    from agent_lab.trading_mission.offline_lane import run_offline_lane, verify_offline_lane
    from agent_lab.trading_mission.topic import mission_id_weekly, render_offline_topic, session_slug_from_topic

    when = datetime.now(_KST)
    topic = render_offline_topic(date_kst=when)
    if args.session is not None:
        session_folder = args.session.expanduser().resolve()
    else:
        slug = session_slug_from_topic(topic)
        session_folder = ROOT / "sessions" / f"{when.strftime('%Y-%m-%d')}-weekly-{slug}"
    session_folder.mkdir(parents=True, exist_ok=True)

    report = run_offline_lane(
        session_folder,
        sync_cards=not args.no_sync,
        push_runtime=not args.no_push,
        force=args.force,
        notes=args.notes,
    )
    verify = verify_offline_lane(session_folder)
    report["verify"] = verify

    run_meta = {
        "session_template": "trading-offline",
        "mission_kind": "trading_weekly",
        "mission_id": mission_id_weekly(when),
        "topic": topic.splitlines()[0] if topic.strip() else "weekly wire-up",
    }
    run_path = session_folder / "run.json"
    if run_path.is_file():
        try:
            existing = json.loads(run_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                existing.update(run_meta)
                run_meta = existing
        except (OSError, json.JSONDecodeError):
            pass
    run_path.write_text(json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("skipped"):
        return 0
    if not report.get("ok"):
        return 1
    if not verify.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
