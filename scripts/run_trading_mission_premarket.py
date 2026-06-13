#!/usr/bin/env python3
"""Run one Trading Mission premarket cycle (P0): preflight → discuss → export → verify."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
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


def _finish(
    folder: Path,
    report: dict,
    *,
    ingest: bool,
    ingest_db: Path | None,
    ingest_dry_run: bool,
) -> int:
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report.get("ok"):
        return 1
    if not ingest:
        return 0

    from agent_lab.trading_mission.ingest_bridge import detect_control_plane_db, ingest_proposal_batch

    db = ingest_db or detect_control_plane_db()
    ingest_report = ingest_proposal_batch(
        folder,
        db_path=db,
        dry_run=ingest_dry_run,
    )
    print("ingest:", json.dumps(ingest_report, ensure_ascii=False, indent=2))
    return 0 if ingest_report.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading Mission premarket (P0)")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run snapshot only; skip Room discuss",
    )
    parser.add_argument(
        "--mock-room",
        action="store_true",
        help="Use AGENT_LAB_MOCK_AGENTS=1 for discuss",
    )
    parser.add_argument(
        "--skip-discuss",
        action="store_true",
        help="Skip Room even when trade allowed (artifact pipeline test)",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="After verify, push proposal_batch to control plane SQLite",
    )
    parser.add_argument(
        "--ingest-db",
        type=Path,
        default=None,
        help="Override control plane SQLite path (default: AGENTIC_TRADING_DB or ~/.agent-lab/)",
    )
    parser.add_argument(
        "--ingest-dry-run",
        action="store_true",
        help="Validate ingest without writing to SQLite",
    )
    args = parser.parse_args()

    _bootstrap_env()

    from agent_lab.trading_mission.token_budget import (
        apply_trading_mission_budget_env,
        resolve_parallel_rounds,
        seed_turn_budget_caps,
    )

    budget = apply_trading_mission_budget_env()
    if args.mock_room:
        os.environ["AGENT_LAB_MOCK_AGENTS"] = "1"

    from agent_lab.agent_health import reconnect_cursor_bridge
    from agent_lab.agents.registry import AGENT_IDS, available_agents
    from agent_lab.quant_utility_validation import detect_pipeline_root
    from agent_lab.room import run_room
    from agent_lab.session import SESSIONS_DIR, session_dir
    from agent_lab.session_setup import merge_setup_permissions, seed_session_setup
    from agent_lab.trading_mission.blocked import write_blocked_artifacts
    from agent_lab.trading_mission.export_batch import build_proposal_batch, write_proposal_batch
    from agent_lab.trading_mission.preflight import build_market_snapshot, write_market_snapshot
    from agent_lab.trading_mission.session_artifacts import (
        append_preflight_seal_to_topic,
        ensure_playbook_after_room,
    )
    from agent_lab.trading_mission.topic import mission_id_from_date, render_premarket_topic
    from agent_lab.trading_mission.verify import check_artifacts

    pipeline = detect_pipeline_root()
    if pipeline is None:
        print("FAIL: pipeline root not found", file=sys.stderr)
        return 1
    os.environ["QUANT_PIPELINE_ROOT"] = str(pipeline)

    topic = render_premarket_topic()
    folder = session_dir(topic[:80], base=SESSIONS_DIR)
    (folder / "topic.txt").write_text(topic, encoding="utf-8")
    seed_turn_budget_caps(folder, budget)

    snapshot = build_market_snapshot(pipeline)
    write_market_snapshot(folder, snapshot)
    topic = append_preflight_seal_to_topic(folder, topic, snapshot)
    print(f"session: {folder.name}")
    print(f"pipeline: {pipeline}")
    print(f"trade_allowed: {snapshot.get('trade_allowed')}")
    print(f"snapshot: {folder / 'artifacts' / 'market_snapshot.json'}")

    if (not snapshot.get("trade_allowed") or args.preflight_only) and not args.mock_room:
        write_blocked_artifacts(folder, snapshot)
        from agent_lab.trading_mission.telemetry import record_mission_telemetry

        record_mission_telemetry(
            folder,
            mission_kind="trading_blocked",
            discuss_skipped=True,
        )
        return _finish(
            folder,
            check_artifacts(folder),
            ingest=args.ingest,
            ingest_db=args.ingest_db,
            ingest_dry_run=args.ingest_dry_run,
        )

    if args.skip_discuss:
        seed_session_setup(
            folder,
            workspace_id="quant-pipeline",
            session_template="trading-mission",
            topic=topic,
        )
        plan_stub = """# plan — Trading Mission (skip-discuss)

## 합의
- ingest_ready: false
- blocking_reason: skip-discuss test mode
- active_strategies: []
- discuss_rounds_used: 0
"""
        (folder / "plan.md").write_text(plan_stub, encoding="utf-8")
        artifacts = folder / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "playbook.md").write_text(
            "# 오늘 장중 행동\n\n## 상태\n- ingest_ready: false\n",
            encoding="utf-8",
        )
        batch = build_proposal_batch(folder, mission_id=mission_id_from_date())
        write_proposal_batch(folder, batch)
        from agent_lab.trading_mission.telemetry import record_mission_telemetry

        record_mission_telemetry(
            folder,
            mission_kind="trading_premarket",
            discuss_skipped=True,
        )
        return _finish(
            folder,
            check_artifacts(folder),
            ingest=args.ingest,
            ingest_db=args.ingest_db,
            ingest_dry_run=args.ingest_dry_run,
        )

    bridge = reconnect_cursor_bridge(workspace=str(pipeline))
    print(
        f"cursor bridge: ok={bridge.get('ok')} bridge={bridge.get('bridge')}",
        flush=True,
    )

    agents = [a for a in AGENT_IDS if a in available_agents()]
    if len(agents) < 3:
        print(f"FAIL: need cursor+codex+claude, got {agents}", file=sys.stderr)
        print("Use --mock-room or set API keys", file=sys.stderr)
        return 1

    seed_session_setup(
        folder,
        workspace_id="quant-pipeline",
        session_template="trading-mission",
        topic=topic,
    )
    perms = merge_setup_permissions({}, "quant-pipeline")

    print(f"agents: {agents}")
    parallel_rounds = resolve_parallel_rounds(1, budget)
    print(f"running discuss ({parallel_rounds} round)...", flush=True)
    t0 = time.perf_counter()

    def on_event(typ: str, payload: dict) -> None:
        if typ == "agent_start":
            print(f"  start {payload.get('agent')}", flush=True)
        elif typ == "agent_done":
            agent = payload.get("agent", "?")
            preview = (payload.get("content") or "")[:100].replace("\n", " ")
            print(f"  done  {agent}: {preview}...", flush=True)

    out_folder, messages, _plan_md = run_room(
        topic,
        agents=agents,
        synthesize=True,
        parallel_rounds=parallel_rounds,
        on_event=on_event,
        session_folder=folder,
        permissions=perms,
        turn_profile="analyze",
    )
    elapsed = time.perf_counter() - t0
    print(f"elapsed: {elapsed:.1f}s")
    print(f"agent replies: {len([m for m in messages if m.role == 'agent'])}")

    if args.mock_room:
        from agent_lab.trading_mission.mock_artifacts import ensure_mock_trading_artifacts

        mock_report = ensure_mock_trading_artifacts(
            out_folder,
            snapshot,
            force_trade_allowed=not snapshot.get("trade_allowed"),
        )
        print("mock artifacts:", json.dumps(mock_report, ensure_ascii=False), flush=True)
    else:
        patched = ensure_playbook_after_room(out_folder)
        if patched:
            print("playbook: auto-sealed from plan consensus", flush=True)

    batch = build_proposal_batch(out_folder, mission_id=mission_id_from_date())
    write_proposal_batch(out_folder, batch)

    from agent_lab.trading_mission.telemetry import record_mission_telemetry

    record_mission_telemetry(
        out_folder,
        mission_kind="trading_premarket",
        wall_ms=elapsed * 1000,
        discuss_skipped=False,
    )

    return _finish(
        out_folder,
        check_artifacts(out_folder),
        ingest=args.ingest,
        ingest_db=args.ingest_db,
        ingest_dry_run=args.ingest_dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
