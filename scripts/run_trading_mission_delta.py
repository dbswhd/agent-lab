#!/usr/bin/env python3
"""Run one Trading Mission delta cycle (P2): snapshot → short discuss → proposal_delta."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
    parser = argparse.ArgumentParser(description="Trading Mission delta (P2)")
    parser.add_argument("--trigger", default="manual", help="Event trigger label")
    parser.add_argument("--reason", default="", help="Human-readable reason")
    parser.add_argument("--skip-discuss", action="store_true", help="Skip Room (pipeline test)")
    parser.add_argument("--mock-room", action="store_true")
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--ingest-dry-run", action="store_true")
    args = parser.parse_args()

    _bootstrap_env()
    if args.mock_room:
        os.environ["AGENT_LAB_MOCK_AGENTS"] = "1"

    from agent_lab.trading_mission.token_budget import (
        apply_trading_mission_budget_env,
        resolve_parallel_rounds,
        seed_turn_budget_caps,
    )

    budget = apply_trading_mission_budget_env()

    from agent_lab.quant_utility_validation import detect_pipeline_root
    from agent_lab.session import SESSIONS_DIR, session_dir
    from agent_lab.session_setup import seed_session_setup
    from agent_lab.trading_mission.delta_export import (
        build_proposal_delta,
        render_delta_topic,
        write_playbook_patch,
        write_proposal_delta,
    )
    from agent_lab.trading_mission.ingest_bridge import detect_control_plane_db, ingest_proposal_batch
    from agent_lab.trading_mission.preflight import build_market_snapshot, write_market_snapshot
    from agent_lab.trading_mission.verify import check_artifacts

    pipeline = detect_pipeline_root()
    if pipeline is None:
        print("FAIL: pipeline root not found", file=sys.stderr)
        return 1
    os.environ["QUANT_PIPELINE_ROOT"] = str(pipeline)

    topic = render_delta_topic(trigger=args.trigger, reason=args.reason)
    folder = session_dir(f"delta-{args.trigger}"[:80], base=SESSIONS_DIR)
    (folder / "topic.txt").write_text(topic, encoding="utf-8")
    seed_turn_budget_caps(folder, budget)

    snapshot = build_market_snapshot(pipeline)
    write_market_snapshot(folder, snapshot)
    print(f"session: {folder.name}")
    print(f"trigger: {args.trigger}")

    seed_session_setup(
        folder,
        workspace_id="quant-pipeline",
        session_template="trading-mission",
        topic=topic,
    )

    if args.skip_discuss:
        plan_stub = f"""# plan — Trading Mission (delta skip-discuss)

## 합의
- ingest_ready: false
- blocking_reason: delta skip-discuss test
- active_strategies: []
- discuss_rounds_used: 0
"""
        (folder / "plan.md").write_text(plan_stub, encoding="utf-8")
        artifacts = folder / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "playbook.md").write_text(
            "# 오늘 장중 행동\n\n## delta\n- skip-discuss\n",
            encoding="utf-8",
        )
        (artifacts / "proposals_draft.json").write_text("[]\n", encoding="utf-8")
    else:
        from agent_lab.agents.registry import AGENT_IDS, available_agents
        from agent_lab.room import run_room
        from agent_lab.session_setup import merge_setup_permissions

        agents = [a for a in AGENT_IDS if a in available_agents()]
        if len(agents) < 3:
            print("FAIL: need 3 agents or use --skip-discuss", file=sys.stderr)
            return 1
        perms = merge_setup_permissions({}, "quant-pipeline")
        folder, _messages, _plan = run_room(
            topic,
            agents=agents,
            synthesize=True,
            parallel_rounds=resolve_parallel_rounds(1, budget),
            session_folder=folder,
            permissions=perms,
            turn_profile="analyze",
        )

    delta = build_proposal_delta(folder, trigger=args.trigger)
    write_proposal_delta(folder, delta)
    write_playbook_patch(folder, delta)

    batch_path = folder / "artifacts" / "proposal_batch.json"
    batch_path.write_text(json.dumps(delta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report = check_artifacts(folder)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report.get("ok"):
        return 1

    if args.ingest or args.ingest_dry_run:
        ingest_report = ingest_proposal_batch(
            folder,
            db_path=detect_control_plane_db(),
            dry_run=args.ingest_dry_run,
        )
        print("ingest:", json.dumps(ingest_report, ensure_ascii=False, indent=2))
        if not ingest_report.get("ok"):
            return 1

    from agent_lab.trading_mission.watcher import mark_queue_done
    from agent_lab.trading_mission.telemetry import record_mission_telemetry

    record_mission_telemetry(
        folder,
        mission_kind="trading_delta",
        discuss_skipped=args.skip_discuss,
    )
    mark_queue_done(args.trigger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
