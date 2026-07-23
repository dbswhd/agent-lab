#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["fastapi>=0.115", "uvicorn>=0.34"]
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: uv run scripts/mission_authority_real_route_harness.py --root /tmp/task6 --port 8765
# 3. Or make executable and run it with the same arguments.
# ──────────────────

"""Real HTTP + disposable-git Mission authority validation.

The harness creates only disposable sessions and repositories below ``--root``.
It never changes product defaults or activates a production cohort.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for import_path in (ROOT, ROOT / "src"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from agent_lab.subprocess_env import subprocess_env
from scripts.mission_authority_cohort_matrix import (
    ExecutionSeed,
    HttpJson,
    git,
    seed_execution,
    seed_repo,
)


@dataclass(frozen=True, slots=True)
class HarnessPaths:
    sessions: Path
    repos: Path
    server_log: Path
    port: int


def _seed_session(paths: HarnessPaths, session_id: str) -> Path:
    folder = paths.sessions / session_id
    folder.mkdir()
    (folder / "plan.md").write_text("# Plan\n\n- ship marker\n", encoding="utf-8")
    (folder / "run.json").write_text(
        json.dumps({"topic": "ship marker", "plan_workflow": {"enabled": True, "phase": "HUMAN_PENDING"}}),
        encoding="utf-8",
    )
    return folder

def _start(paths: HarnessPaths, cohort: str) -> subprocess.Popen[bytes]:
    env = subprocess_env(
        AGENT_LAB_SESSIONS_DIR=str(paths.sessions),
        AGENT_LAB_MOCK_AGENTS="1",
        AGENT_LAB_MISSION_DUAL_WRITE="1",
        AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY="1",
        AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY="1",
        AGENT_LAB_MISSION_AUTHORITY="1",
        AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS=cohort,
        AGENT_LAB_MISSION_AUTHORITY_SESSIONS=cohort,
    )
    log = paths.server_log.open("a", encoding="utf-8")
    return subprocess.Popen(
        [
            str(ROOT / ".venv" / "bin" / "uvicorn"),
            "app.server.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(paths.port),
        ],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _await_health(http: HttpJson) -> None:
    for _ in range(100):
        if http.healthy():
            return
        time.sleep(0.1)
    raise RuntimeError("server did not become healthy")


def _kill(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def run(paths: HarnessPaths) -> dict[str, object]:
    paths.sessions.mkdir(parents=True)
    paths.repos.mkdir(parents=True)
    cohort = "task6-both"
    dirty_id = "task6-dirty"
    misleading_id = "task6-misleading"
    allowlist = ",".join((cohort, dirty_id, misleading_id))
    folder = _seed_session(paths, cohort)
    repo = seed_repo(paths.repos, cohort)
    dirty_folder = _seed_session(paths, dirty_id)
    dirty_repo = seed_repo(paths.repos, dirty_id)
    misleading_folder = _seed_session(paths, misleading_id)
    misleading_repo = seed_repo(paths.repos, misleading_id)
    http = HttpJson(paths.port)
    first = _start(paths, allowlist)
    try:
        _await_health(http)
        approve = http.request("POST", f"/api/sessions/{cohort}/plan/approve", {"goal": "ship marker"})
        opened = http.request(
            "POST",
            f"/api/sessions/{cohort}/inbox/items",
            {"kind": "question", "prompt": "Proceed?", "source": "mcp"},
        )
        item = opened[1]["item"]
        item_id = str(item["id"]) if isinstance(item, dict) else ""
        resolved = http.request(
            "POST",
            f"/api/sessions/{cohort}/inbox/{item_id}/resolve",
            {"selected": ["go"], "expected_version": 0, "append_chat": False},
        )
    finally:
        _kill(first)

    second = _start(paths, allowlist)
    try:
        _await_health(http)
        replay = http.request("GET", f"/api/sessions/{cohort}/mission/read-model")
        journal = folder / ".agent-lab" / "mission-events.jsonl"
        event_count_before_duplicate = len(journal.read_text(encoding="utf-8").splitlines())
        duplicate = http.request(
            "POST",
            f"/api/sessions/{cohort}/inbox/{item_id}/resolve",
            {"selected": ["go"], "expected_version": 0, "append_chat": False},
        )
        event_count_after_duplicate = len(journal.read_text(encoding="utf-8").splitlines())
        malformed = http.request(
            "POST",
            f"/api/sessions/{cohort}/inbox/{item_id}/resolve",
            {"expected_version": -1},
        )
        seed_execution(ExecutionSeed(folder, repo, "exec-pass", "`v2`"))
        merged = http.request(
            "POST",
            f"/api/sessions/{cohort}/execute/resolve",
            {"execution_id": "exec-pass", "vote": "approve"},
        )
        reverified = http.request(
            "POST",
            f"/api/sessions/{cohort}/execute/reverify",
            {"execution_id": "exec-pass"},
        )
        http.request("POST", f"/api/sessions/{dirty_id}/plan/approve", {"goal": "dirty guard"})
        seed_execution(ExecutionSeed(dirty_folder, dirty_repo, "exec-dirty", "`v2`"))
        (dirty_repo / "src" / "app.py").write_text("uncommitted\n", encoding="utf-8")
        dirty = http.request(
            "POST",
            f"/api/sessions/{dirty_id}/execute/resolve",
            {"execution_id": "exec-dirty", "vote": "approve"},
        )
        http.request("POST", f"/api/sessions/{misleading_id}/plan/approve", {"goal": "oracle guard"})
        seed_execution(
            ExecutionSeed(
                misleading_folder,
                misleading_repo,
                "exec-misleading",
                "`src/app.py` contains `NEVER_PRESENT`",
            )
        )
        misleading = http.request(
            "POST",
            f"/api/sessions/{misleading_id}/execute/resolve",
            {"execution_id": "exec-misleading", "vote": "approve"},
        )
        misleading_read = http.request(
            "GET",
            f"/api/sessions/{misleading_id}/mission/read-model",
        )
    finally:
        _kill(second)

    rollback = "task6-rollback"
    _seed_session(paths, rollback)
    third = _start(paths, "")
    try:
        _await_health(http)
        rolled_back = http.request(
            "POST",
            f"/api/sessions/{rollback}/plan/approve",
            {"goal": "legacy"},
        )
    finally:
        _kill(third)

    merge_body = merged[1]
    execution = merge_body.get("execution")
    oracle = execution.get("oracle") if isinstance(execution, dict) else {}
    misleading_execution = misleading[1].get("execution")
    misleading_oracle = (
        misleading_execution.get("oracle") if isinstance(misleading_execution, dict) else {}
    )
    rollback_bridge = rolled_back[1].get("mission_dual_write")
    replay_items = replay[1].get("inbox_items")
    parity_zero = (
        replay[1].get("state") == "READY_TO_EXECUTE"
        and isinstance(replay_items, list)
        and bool(replay_items)
        and replay_items[0].get("status") == "resolved"
    )
    passed = (
        approve[0] == opened[0] == resolved[0] == replay[0] == merged[0] == reverified[0] == 200
        and duplicate[0] == 409
        and event_count_before_duplicate == event_count_after_duplicate
        and malformed[0] == 422
        and parity_zero
        and dirty[0] == 400
        and isinstance(oracle, dict)
        and oracle.get("verdict") == "pass"
        and misleading[0] == 200
        and isinstance(misleading_oracle, dict)
        and misleading_oracle.get("verdict") == "fail"
        and misleading_read[1].get("state") == "VERIFYING"
        and isinstance(rollback_bridge, dict)
        and rollback_bridge.get("reason") == "cohort_allowlist_empty"
        and (repo / "src" / "app.py").read_text(encoding="utf-8") == "v2\n"
    )
    return {
        "pass": passed,
        "activation_performed": False,
        "human_go_required_before_activation": True,
        "plan_approve": approve[0],
        "inbox_open_resolve": [opened[0], resolved[0]],
        "restart_pids": [first.pid, second.pid],
        "restart_read_model": replay[0],
        "parity_divergence": 0 if parity_zero else 1,
        "duplicate_stale": duplicate[0],
        "duplicate_event_delta": event_count_after_duplicate - event_count_before_duplicate,
        "malformed": malformed[0],
        "execute_merge_oracle": [merged[0], oracle.get("verdict") if isinstance(oracle, dict) else None],
        "reverify": reverified[0],
        "dirty_worktree_blocked": dirty[0],
        "misleading_http_success": [
            misleading[0],
            misleading_oracle.get("verdict") if isinstance(misleading_oracle, dict) else None,
            misleading_read[1].get("state"),
        ],
        "rollback_legacy_first": [rolled_back[0], rollback_bridge],
        "git_head": git(repo, "rev-parse", "HEAD"),
        "server_log": str(paths.server_log),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    paths = HarnessPaths(
        sessions=args.root / "sessions",
        repos=args.root / "repos",
        server_log=args.root / "server.log",
        port=args.port,
    )
    report = run(paths)
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
