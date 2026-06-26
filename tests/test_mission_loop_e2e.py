"""Mock E2E: verified profile → mission FSM through Room + execute pipeline."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agent_mocks import disable_execute_inbox_mcp

from agent_lab.mission_loop import get_mission_loop
from agent_lab.plan_actions import find_dry_run_action
from agent_lab.plan_execute import resolve_execution
from agent_lab.plan_pending import PlanSnapshotRequired, approve_pending_plan, ensure_plan_snapshot_approved
from agent_lab.room import continue_room_round
from agent_lab.run_meta import patch_run_meta, read_run_meta
from agent_lab.runtime.events import RuntimeEvent
import agent_lab.runtime.runtime as runtime_module
from agent_lab.verified_loop import (
    approve_verified_loop,
    init_verified_loop,
    record_proposed_goal,
)


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def _good_plan() -> str:
    return """# Plan

## 지금 실행

1. Fix auth module
   - 무엇을: JWT validation in `src/app.py`
   - 어디서: `src/app.py`
   - 검증: `src/app.py` contains `AUTH_OK`
"""


def _seed_approved_plan_snapshot(folder: Path, plan_md: str) -> None:
    action = find_dry_run_action(plan_md, 1, kind="now")
    assert action is not None
    try:
        ensure_plan_snapshot_approved(folder, action, plan_md)
    except PlanSnapshotRequired as exc:
        approve_pending_plan(folder, exc.pending_plan["id"])


def _mission_phase(folder: Path) -> str:
    return str(get_mission_loop(read_run_meta(folder)).get("phase") or "")


@pytest.fixture
def mission_e2e_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_MISSION_LOOP", "1")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

    folder = tmp_path / "sess-mission-e2e"
    folder.mkdir()
    (folder / "topic.txt").write_text("mission mock e2e\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        json.dumps({"role": "user", "content": "seed", "ts": "t0"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "topic": "mission mock e2e",
                "agents": ["cursor", "codex", "claude"],
                "status": "idle",
                "turns": [],
                "actions": [],
                "approvals": [],
                "executions": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return folder


def test_verified_mission_loop_mock_e2e_full_fsm(
    mission_e2e_session: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Room discuss → scribe/plan gate → dry-run → merge verify → MISSION_DONE (mock-only)."""
    disable_execute_inbox_mcp(monkeypatch)
    folder = mission_e2e_session
    git_repo = _init_repo(tmp_path / "git-root")

    events_seen: list[str] = []

    real_dispatch = runtime_module.dispatch

    def _track_dispatch(
        session: Path,
        event: RuntimeEvent | str,
        payload: dict[str, Any] | None = None,
    ):
        events_seen.append(str(event))
        return real_dispatch(session, event, payload)

    monkeypatch.setattr(runtime_module, "dispatch", _track_dispatch)

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)

    def _mock_execute(**kwargs: Any) -> str:
        cwd = Path(kwargs["cwd"])
        target = cwd / "src" / "app.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("AUTH_OK\n", encoding="utf-8")
        return "VERIFICATION: PASS"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _mock_execute)
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (git_repo, {}),
    )

    phases_seen: list[str] = []

    def _record_phase() -> str:
        phase = _mission_phase(folder)
        if not phases_seen or phases_seen[-1] != phase:
            phases_seen.append(phase)
        return phase

    init_verified_loop(folder)
    record_proposed_goal(
        folder,
        {
            "goal": "Fix JWT validation in src/app.py with AUTH_OK marker",
            "completion_promise": "MISSION_DONE",
            "criteria": "AUTH_OK in src/app.py",
        },
        source="e2e",
    )

    def _pending(run: dict[str, Any]) -> dict[str, Any]:
        run["verified_loop"]["status"] = "pending_approval"
        return run

    patch_run_meta(folder, _pending)
    approve_verified_loop(folder)

    assert _record_phase() == "DISCUSS"
    run = read_run_meta(folder)
    assert run["mission_loop"]["enabled"] is True
    assert run["verified_loop"]["status"] == "running"

    messages, _plan = continue_room_round(
        folder,
        "Discuss: scope JWT validation for mission e2e.",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        parallel_rounds=1,
    )
    agent_replies = [m for m in messages if m.role == "agent" and (m.content or "").strip()]
    assert agent_replies, "mock discuss should produce agent replies"
    assert all("[mock:" in (m.content or "") for m in agent_replies)

    run_after_discuss = read_run_meta(folder)
    assert run_after_discuss["mission_loop"]["enabled"] is True
    assert run_after_discuss["mission_loop"]["phase"] == "DISCUSS"
    _record_phase()

    plan_md = _good_plan()
    (folder / "plan.md").write_text(plan_md, encoding="utf-8")
    _seed_approved_plan_snapshot(folder, plan_md)

    scribe_out = runtime_module.dispatch(folder, RuntimeEvent.SCRIBE_COMPLETE, {"plan_md": plan_md})
    assert scribe_out.handled is True
    phase_after_gate = _record_phase()
    assert phase_after_gate in {"EXECUTE_QUEUE", "MERGE_REVIEW", "DRY_RUN"}

    if _mission_phase(folder) == "EXECUTE_QUEUE":
        advance_out = runtime_module.dispatch(folder, RuntimeEvent.MISSION_ADVANCE)
        assert advance_out.handled is True
        phase_after_gate = _record_phase()

    assert phase_after_gate == "MERGE_REVIEW", phases_seen

    run = read_run_meta(folder)
    executions = [row for row in run.get("executions") or [] if isinstance(row, dict)]
    pending = next((row for row in executions if row.get("status") == "pending_approval"), None)
    assert pending is not None, f"expected pending execution, got {executions!r}"

    merge_out = resolve_execution(
        folder,
        execution_id=str(pending["id"]),
        vote="approve",
        permissions={},
    )
    assert merge_out["execution"]["status"] == "merged"
    assert merge_out["execution"]["oracle"]["verdict"] == "pass"
    assert _record_phase() == "MISSION_DONE"

    final = read_run_meta(folder)
    ml = get_mission_loop(final)
    assert ml.get("pending_action_indices") == []
    assert ml.get("circuit_breaker") is False

    required_events = {
        "mission.enable",
        "scribe.complete",
        "mission.plan_gate",
        "mission.advance",
        "execute.dry_run.start",
        "execute.dry_run.complete",
        "execute.verify.pass",
    }
    assert required_events.issubset(set(events_seen)), (
        f"missing runtime events: {required_events - set(events_seen)}; seen={events_seen}"
    )

    required_phases = {"DISCUSS", "MERGE_REVIEW", "MISSION_DONE"}
    assert required_phases.issubset(set(phases_seen)), (
        f"missing phases: {required_phases - set(phases_seen)}; seen={phases_seen}"
    )
