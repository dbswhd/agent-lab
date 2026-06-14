#!/usr/bin/env python3
"""Run one live discuss turn with quant-pipeline workspace preset."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bootstrap_env() -> None:
    """Match API startup: ~/.agent-lab + repo .env so CURSOR_API_KEY is visible."""
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


TOPIC = (
    "[quant-pipeline preset 검증] research/kr/results 아래 backtest verdict를 읽고, "
    "quant-control 앱에 wire-up할 만한 PASS 후보가 있으면 1개만 골라 "
    "근거 파일 경로 + 이유 3줄. 없으면 sector_rotation FAIL처럼 보류 사유만."
)


def main() -> int:
    _bootstrap_env()

    from agent_lab.agent_health import reconnect_cursor_bridge
    from agent_lab.agents.registry import AGENT_IDS, available_agents
    from agent_lab.quant_utility_validation import detect_pipeline_root
    from agent_lab.room import run_room
    from agent_lab.session import session_dir, SESSIONS_DIR
    from agent_lab.session_setup import merge_setup_permissions, seed_session_setup

    pipeline = detect_pipeline_root()
    if pipeline is None:
        print("FAIL: pipeline root not found (QUANT_PIPELINE_ROOT or ~/Desktop/pipeline)", file=sys.stderr)
        return 1
    os.environ["QUANT_PIPELINE_ROOT"] = str(pipeline)

    bridge = reconnect_cursor_bridge(workspace=str(pipeline))
    print(
        f"cursor bridge: ok={bridge.get('ok')} bridge={bridge.get('bridge')} hint={bridge.get('hint') or '(none)'}",
        flush=True,
    )

    agents = [a for a in AGENT_IDS if a in available_agents()]
    if len(agents) < 3:
        print(f"FAIL: need cursor+codex+claude, got {agents}", file=sys.stderr)
        print("Set CURSOR_API_KEY in .env and: pip install -e '.[cursor]'", file=sys.stderr)
        return 1

    folder = session_dir(TOPIC[:80], base=SESSIONS_DIR)
    (folder / "topic.txt").write_text(TOPIC + "\n", encoding="utf-8")
    seed_session_setup(
        folder,
        workspace_id="quant-pipeline",
        session_template="general",
        topic=TOPIC,
    )
    perms = merge_setup_permissions({}, "quant-pipeline")

    print(f"session: {folder.name}")
    print(f"pipeline: {pipeline}")
    print(f"agents: {agents}")
    print("running discuss (1 round)...", flush=True)

    t0 = time.perf_counter()
    events: list[tuple[str, str]] = []

    def on_event(typ: str, payload: dict) -> None:
        if typ == "agent_start":
            print(f"  start {payload.get('agent')}", flush=True)
        elif typ == "agent_done":
            agent = payload.get("agent", "?")
            preview = (payload.get("content") or "")[:120].replace("\n", " ")
            print(f"  done  {agent}: {preview}...", flush=True)
            events.append((agent, payload.get("content") or ""))
        elif typ == "error":
            print(f"  ERROR: {payload.get('message')}", file=sys.stderr, flush=True)

    out_folder, messages, plan_md = run_room(
        TOPIC,
        agents=agents,
        synthesize=False,
        parallel_rounds=1,
        on_event=on_event,
        session_folder=folder,
        permissions=perms,
        turn_profile="analyze",
    )
    elapsed = time.perf_counter() - t0

    run = json.loads((out_folder / "run.json").read_text(encoding="utf-8"))
    last_turn = (run.get("turns") or [])[-1] if run.get("turns") else {}
    turn_perms = last_turn.get("permissions") or {}
    binding = run.get("workspace_binding") or {}

    print()
    print(f"elapsed: {elapsed:.1f}s")
    print(f"workspace_binding: {binding.get('preset')} -> {binding.get('path')}")
    print(f"local_pipeline: {(turn_perms.get('cursor') or {}).get('local_pipeline')}")
    print(f"agent replies: {len([m for m in messages if m.role == 'agent'])}")

    for m in messages:
        if m.role != "agent":
            continue
        label = m.agent or "?"
        body = (m.content or "").strip()
        print(f"\n--- {label} ({len(body)} chars) ---")
        print(body[:2000])
        if len(body) > 2000:
            print("... [truncated]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
