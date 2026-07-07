#!/usr/bin/env python3
"""X2 lift dogfood — mock Room + execute path after P1/P2 (no UI).

Validates TurnPolicy routing (turn_profile=free, FSM not short-circuited) and
emits execute-phase outcome ledger rows for ``make x2-lift-dogfood-check``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "src", ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

TOPIC = (
    "docs 오타 1건 수정 plan action을 만들어 dry-run → 승인 → merge → "
    "Oracle PASS까지 진행해 주세요."
)

DOC_PLAN = """# Docs typo (X2 dogfood)

## 지금 실행

1. Fix docs marker
   - 무엇을: docs/README.md에 X2_DOGFOOD_OK 마커 추가
   - 어디서: `docs/README.md`
   - 검증: docs/README.md 파일에 마커 추가됨
"""


def _utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _seed_approved_plan_snapshot(folder: Path, plan_md: str) -> None:
    from agent_lab.plan.actions import find_dry_run_action
    from agent_lab.plan.pending import PlanSnapshotRequired, approve_pending_plan, ensure_plan_snapshot_approved

    action = find_dry_run_action(plan_md, 1, kind="now")
    if action is None:
        raise RuntimeError("plan action #1 not found")
    try:
        ensure_plan_snapshot_approved(folder, action, plan_md)
    except PlanSnapshotRequired as exc:
        approve_pending_plan(folder, exc.pending_plan["id"])


def main() -> int:
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
    os.environ.setdefault("AGENT_LAB_TURN_POLICY", "1")
    os.environ.setdefault("AGENT_LAB_TURN_METRICS", "1")
    os.environ.setdefault("AGENT_LAB_OUTCOME_LEDGER", "1")
    os.environ.setdefault("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    os.environ.setdefault("AGENT_LAB_FEEDBACK_EXPLORE_RATE", "0")
    os.environ.setdefault("AGENT_LAB_CLARIFIER", "0")
    os.environ.setdefault("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "0")
    os.environ.setdefault("AGENT_LAB_ROOM_PRESET", "supervisor")

    tests_dir = ROOT / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    from agent_mocks import disable_execute_inbox_mcp

    import pytest

    monkeypatch = pytest.MonkeyPatch()
    disable_execute_inbox_mcp(monkeypatch)

    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    sessions_dir = ROOT / "sessions"
    sessions_dir.mkdir(exist_ok=True)
    session_mod.SESSIONS_DIR = sessions_dir
    deps_mod.SESSIONS_DIR = sessions_dir

    peer_calls = {"n": 0}

    def _fake_peer_review(_folder: Path, *_args: object, **_kwargs: object) -> list[object]:
        peer_calls["n"] += 1
        return []

    def _fake_synthesize_plan(*_args: object, **_kwargs: object) -> str:
        return DOC_PLAN

    checks: list[tuple[str, bool, object]] = []

    with (
        patch("agent_lab.plan.workflow.run_plan_peer_review_round", _fake_peer_review),
        patch("agent_lab.room.synthesize_plan", _fake_synthesize_plan),
    ):
        from agent_lab import room

        folder, _messages, plan_md = room.run_room(
            TOPIC,
            agents=["cursor", "codex", "claude"],
            synthesize=True,
            sessions_base=sessions_dir,
            turn_profile="loop",
        )

    from agent_lab.run.meta import read_run_meta
    from agent_lab.plan.workflow import approve_plan, get_plan_workflow, set_plan_workflow_phase

    run = read_run_meta(folder)
    last_turn = (run.get("turns") or [{}])[-1]
    tp_snap = last_turn.get("turn_policy") if isinstance(last_turn, dict) else {}
    routing = (tp_snap.get("routing_contract") or {}) if isinstance(tp_snap, dict) else {}
    turn_profile_snap = last_turn.get("turn_profile") if isinstance(last_turn, dict) else None

    checks.append(("turn_profile=free", turn_profile_snap == "free", turn_profile_snap))
    checks.append(
        ("discuss_light=false", routing.get("discuss_light") is False, routing.get("discuss_light")),
    )
    checks.append(
        (
            "plan_execute_intent=true",
            routing.get("plan_execute_intent") is True,
            routing.get("plan_execute_intent"),
        ),
    )
    checks.append(
        (
            "skip_fsm_bootstrap=false",
            not bool(routing.get("skip_fsm_bootstrap")),
            routing.get("skip_fsm_bootstrap"),
        ),
    )

    pw = get_plan_workflow(run)
    checks.append(("plan_workflow enabled", bool(pw.get("enabled")), pw.get("phase")))
    if pw.get("phase") not in {"HUMAN_PENDING", "APPROVED"}:
        set_plan_workflow_phase(folder, "HUMAN_PENDING")
    plan_path = folder / "plan.md"
    if not plan_path.is_file() or not plan_path.read_text(encoding="utf-8").strip():
        plan_path.write_text(DOC_PLAN, encoding="utf-8")
    if pw.get("phase") != "APPROVED":
        approve_plan(folder)
    checks.append(
        ("plan approved", get_plan_workflow(read_run_meta(folder)).get("phase") == "APPROVED", pw.get("phase")),
    )

    workspace = Path(tempfile.mkdtemp(prefix="x2-dogfood-ws-"))
    docs = workspace / "docs"
    docs.mkdir()
    shutil.copy(ROOT / "docs" / "README.md", docs / "README.md")

    def _mock_cursor(**_kwargs: object) -> str:
        readme = docs / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nX2_DOGFOOD_OK\n", encoding="utf-8")
        return "added X2_DOGFOOD_OK marker"

    from agent_lab.plan.execute import resolve_execution, run_dry_run

    with (
        patch("agent_lab.agents.cursor_agent.is_available", lambda: True),
        patch("agent_lab.agents.cursor_agent.respond", _mock_cursor),
        patch(
            "agent_lab.plan.execute.resolve_execute_workspace",
            lambda _permissions=None, _expected=None: (workspace, {}),
        ),
    ):
        _seed_approved_plan_snapshot(folder, DOC_PLAN)
        execution = run_dry_run(folder, action_index=1, permissions={})
        resolve_execution(folder, execution_id=execution["id"], vote="approve", permissions={})

    run = read_run_meta(folder)
    ex = (run.get("executions") or [])[-1]
    oracle = ex.get("oracle") or (ex.get("verify_after_merge") or {}).get("oracle") or {}
    checks.append(("dry_run pending", execution.get("status") == "pending_approval", execution.get("status")))
    checks.append(("execution done", ex.get("status") in {"merged", "completed"}, ex.get("status")))
    checks.append(("oracle pass", oracle.get("verdict") == "pass", oracle.get("verdict")))

    from agent_lab.outcome_harvester import outcomes_path

    ledger = outcomes_path()
    execute_rows = 0
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("phase") == "execute" and row.get("session_id") == folder.name:
                execute_rows += 1
    checks.append(("execute ledger row", execute_rows >= 1, execute_rows))

    report = {
        "session": str(folder),
        "peer_review_rounds": peer_calls["n"],
        "plan_md_chars": len(plan_md or ""),
        "checks": [{"name": n, "ok": ok, "got": got} for n, ok, got in checks],
        "outcomes_path": str(ledger),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    failed = [c for c in checks if not c[1]]
    if failed:
        for name, _ok, got in failed:
            print(f"FAIL: {name} — got {got!r}", file=sys.stderr)
        return 1
    print(f"OK: x2 lift dogfood passed — session {folder.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
