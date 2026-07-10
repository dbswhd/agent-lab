#!/usr/bin/env python3
"""X2 lift dogfood — mock Room + execute path after P1/P2 (no UI).

Uses ``docs/_dogfood/x2-lift.md`` reversible marker (not product docs).

Public entry for suite / progress automation:
  ``run_x2_lift_mock(sessions_base=...)`` → result dict (ok, session, checks, …).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for _p in (ROOT / "src", SCRIPTS, ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from x2_lift_dogfood_config import (  # noqa: E402
    DOGFood_PATH,
    DOGFood_REL,
    MARKER_LINE_HINT,
    MARKER_WRONG,
    PLAN_MD,
    TOPIC,
    apply_typo,
    has_typo,
)


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


@contextmanager
def _isolated_config_dir() -> Any:
    """Keep mock run-lock state away from any live local server."""
    previous = os.environ.get("AGENT_LAB_CONFIG_DIR")
    with tempfile.TemporaryDirectory(prefix="x2-dogfood-config-") as tmp:
        os.environ["AGENT_LAB_CONFIG_DIR"] = tmp
        try:
            yield Path(tmp)
        finally:
            if previous is None:
                os.environ.pop("AGENT_LAB_CONFIG_DIR", None)
            else:
                os.environ["AGENT_LAB_CONFIG_DIR"] = previous


def run_x2_lift_mock(
    *,
    sessions_base: Path | None = None,
    restore_fixture: bool = True,
) -> dict[str, Any]:
    """Plan → approve → dry-run → merge → Oracle PASS (mock agents + mock cursor).

    Does **not** bypass Human gates: plan approval and execute resolve are
    called explicitly (same as a Human clicking Approve in the UI).
    """
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
    os.environ.setdefault("AGENT_LAB_TURN_POLICY", "1")
    os.environ.setdefault("AGENT_LAB_TURN_METRICS", "1")
    os.environ.setdefault("AGENT_LAB_OUTCOME_LEDGER", "1")
    os.environ.setdefault("AGENT_LAB_FEEDBACK_ADVISOR", "1")
    os.environ.setdefault("AGENT_LAB_FEEDBACK_EXPLORE_RATE", "0")
    os.environ.setdefault("AGENT_LAB_CLARIFIER", "0")
    os.environ.setdefault("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "0")
    os.environ.setdefault("AGENT_LAB_ROOM_PRESET", "supervisor")
    os.environ.setdefault("AGENT_LAB_DOGFOOD_EXECUTE_OUTCOMES", "1")
    # Force mock oracle: live oracle env may bleed in from server env
    os.environ["AGENT_LAB_ORACLE_LIVE"] = "0"

    apply_typo()

    tests_dir = ROOT / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    from agent_mocks import disable_execute_inbox_mcp

    import pytest

    monkeypatch = pytest.MonkeyPatch()
    disable_execute_inbox_mcp(monkeypatch)

    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    sessions_dir = sessions_base if sessions_base is not None else (ROOT / "sessions")
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_mod.SESSIONS_DIR = sessions_dir
    deps_mod.SESSIONS_DIR = sessions_dir

    peer_calls = {"n": 0}

    def _fake_peer_review(_folder: Path, *_args: object, **_kwargs: object) -> list[object]:
        peer_calls["n"] += 1
        return []

    def _fake_synthesize_plan(*_args: object, **_kwargs: object) -> str:
        return PLAN_MD

    checks: list[tuple[str, bool, object]] = []
    checks.append(("dogfood typo seeded", has_typo(), str(DOGFood_PATH)))

    try:
        with _isolated_config_dir():
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
                plan_path.write_text(PLAN_MD, encoding="utf-8")
            if pw.get("phase") != "APPROVED":
                approve_plan(folder)
            checks.append(
                ("plan approved", get_plan_workflow(read_run_meta(folder)).get("phase") == "APPROVED", pw.get("phase")),
            )

            workspace = Path(tempfile.mkdtemp(prefix="x2-dogfood-ws-"))
            dogfood_dir = workspace / DOGFood_REL.parent
            dogfood_dir.mkdir(parents=True)
            shutil.copy(DOGFood_PATH, workspace / DOGFood_REL)

            def _mock_cursor(**_kwargs: object) -> str:
                target = workspace / DOGFood_REL
                text = target.read_text(encoding="utf-8")
                if MARKER_WRONG in text:
                    lines = text.splitlines(keepends=True)
                    fixed = [
                        line.replace(MARKER_WRONG, "room.py에서", 1)
                        if MARKER_WRONG in line and MARKER_LINE_HINT in line
                        else line
                        for line in lines
                    ]
                    target.write_text("".join(fixed), encoding="utf-8")
                return f"fixed {DOGFood_REL}"

            from agent_lab.plan.execute import resolve_execution, run_dry_run

            with (
                patch("agent_lab.agents.cursor_agent.is_available", lambda: True),
                patch("agent_lab.agents.cursor_agent.respond", _mock_cursor),
                patch(
                    "agent_lab.plan.execute.resolve_execute_workspace",
                    lambda _permissions=None, _expected=None: (workspace, {}),
                ),
            ):
                _seed_approved_plan_snapshot(folder, PLAN_MD)
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

            failed = [c for c in checks if not c[1]]
            return {
                "ok": len(failed) == 0,
                "session": str(folder),
                "session_id": folder.name,
                "dogfood_file": str(DOGFood_REL),
                "peer_review_rounds": peer_calls["n"],
                "plan_md_chars": len(plan_md or ""),
                "oracle_verdict": oracle.get("verdict"),
                "execution_status": ex.get("status"),
                "checks": [{"name": n, "ok": ok, "got": got} for n, ok, got in checks],
                "outcomes_path": str(ledger),
                "failed": [{"name": n, "got": got} for n, _ok, got in failed],
            }
    finally:
        monkeypatch.undo()
        if restore_fixture:
            # Leave fixture in typo state for the next dogfood batch.
            apply_typo()


def main() -> int:
    report = run_x2_lift_mock()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not report["ok"]:
        for row in report.get("failed") or []:
            print(f"FAIL: {row['name']} — got {row['got']!r}", file=sys.stderr)
        return 1
    print(f"OK: x2 lift dogfood passed — session {report['session_id']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
