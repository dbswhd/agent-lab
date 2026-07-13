"""Human cutover 판정용: production HTTP route를 통한 dual-write cohort + rollback 검증.

이전 evidence(scripts/mission_dual_write_evidence.py)는 kernel/repository를 직접 호출하는
production-like harness였다. 이 스크립트는 실제 FastAPI production route
(POST /plan/approve, /plan/reject, /inbox/{id}/resolve, /execute/resolve,
/execute/merge/confirm, /execute/reverify)를 TestClient로 호출하고, 대상 sessions
디렉터리는 호출자가 지정한다(운영 sessions directory를 가리킬 수 있음).

각 세션은 별도 함수로 구성되며, route 호출 후 mission_dual_write 브리지 결과와
/mission/read-model parity를 함께 기록한다. 후반부는 AGENT_LAB_MISSION_DUAL_WRITE를
끈 상태에서 (a) 신규 세션이 legacy-only로 동작하는지, (b) 이미 dual-write로 mirrored된
세션이 flag OFF 이후에도 legacy route가 계속 정상 동작하는지(rollback 안전성)를 검증한다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SAMPLE_PLAN = """# Demo feature

## 지금 실행

1. Add widget
   - 무엇을: implement widget
   - 어디서: `src/widget.py`
   - 검증: `pytest tests/test_widget.py`
"""


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check)
    return result.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def _commit_all(wt: Path, msg: str) -> None:
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", msg)


def _client(sessions_root: Path) -> Any:
    from fastapi.testclient import TestClient
    from agent_lab.session import paths as session_paths
    from agent_lab import session as session_module
    import app.server.deps as deps_mod
    from app.server.main import create_app

    session_paths.SESSIONS_DIR = sessions_root
    session_module.SESSIONS_DIR = sessions_root
    deps_mod.SESSIONS_DIR = sessions_root
    return TestClient(create_app(bootstrap=False))


def _read_model(client: Any, session_id: str) -> dict[str, Any]:
    response = client.get(f"/api/sessions/{session_id}/mission/read-model")
    response.raise_for_status()
    return response.json()


def _journal_exists(folder: Path) -> bool:
    return (folder / ".agent-lab" / "mission-events.jsonl").is_file()


def _init_session(sessions_root: Path, name: str, *, with_plan: bool = True) -> Path:
    folder = sessions_root.resolve() / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "topic.txt").write_text(name, encoding="utf-8")
    (folder / "chat.jsonl").write_text("", encoding="utf-8")
    if with_plan:
        (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text(json.dumps({"topic": name}), encoding="utf-8")
    return folder


def _scenario_plan_approve(client: Any, sessions_root: Path, name: str) -> dict[str, Any]:
    from agent_lab.plan.workflow_state import set_plan_workflow_phase

    folder = _init_session(sessions_root, name)
    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    response = client.post(f"/api/sessions/{name}/plan/approve", json={"goal": "ship widget"})
    body = response.json()
    read_model = _read_model(client, name)
    return {
        "session_id": name,
        "route": "POST /plan/approve",
        "status_code": response.status_code,
        "mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "plan_workflow_phase": body.get("plan_workflow", {}).get("phase"),
        "read_model_migrated": read_model.get("migrated"),
        "read_model_state": read_model.get("state"),
    }


def _scenario_plan_reject(client: Any, sessions_root: Path, name: str) -> dict[str, Any]:
    from agent_lab.plan.workflow_state import set_plan_workflow_phase

    folder = _init_session(sessions_root, name)
    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    response = client.post(
        f"/api/sessions/{name}/plan/reject",
        json={"note": "revise scope", "target_phase": "CLARIFY"},
    )
    body = response.json()
    read_model = _read_model(client, name)
    return {
        "session_id": name,
        "route": "POST /plan/reject",
        "status_code": response.status_code,
        "mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "plan_workflow_phase": body.get("plan_workflow", {}).get("phase"),
        "read_model_migrated": read_model.get("migrated"),
        "read_model_state": read_model.get("state"),
    }


def _scenario_inbox_resolve(client: Any, sessions_root: Path, name: str) -> dict[str, Any]:
    from agent_lab.human_inbox import create_inbox_item
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import BlockExecution

    folder = _init_session(sessions_root, name)
    MissionApplication(folder, "ship widget").approve_plan()
    MissionApplication(folder, "ship widget").repository.dispatch(BlockExecution("human decision"))
    item = create_inbox_item(folder, kind="question", source="dual-write-route-cohort", prompt="Resume?")
    response = client.post(f"/api/sessions/{name}/inbox/{item['id']}/resolve", json={"decision": "go"})
    body = response.json()
    read_model = _read_model(client, name)
    return {
        "session_id": name,
        "route": "POST /inbox/{item}/resolve",
        "status_code": response.status_code,
        "mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "inbox_pending": body.get("inbox_pending"),
        "read_model_migrated": read_model.get("migrated"),
        "read_model_state": read_model.get("state"),
    }


def _worktree_execution_row(*, exec_id: str, ew: Any, status: str) -> dict[str, Any]:
    return {
        "id": exec_id,
        "status": status,
        "isolation_effective": "worktree",
        "action_index": 1,
        "action_kind": "now",
        "action_id": "plan-action-now-1",
        "action_what": "implement widget",
        "action_where": "`src/widget.py`",
        "action_verify": "`pytest tests/test_widget.py`",
        "paths_outside_expected": [],
        **ew.to_dict(),
    }


def _prep_plan_approve(client: Any, folder: Path, name: str) -> bool:
    """Bring the session (legacy + Mission bridge) to READY_TO_EXECUTE via the real route."""
    from agent_lab.plan.workflow_state import set_plan_workflow_phase

    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    response = client.post(f"/api/sessions/{name}/plan/approve", json={"goal": "ship widget"})
    body = response.json()
    return response.status_code == 200 and body.get("mission_dual_write", {}).get("mirrored") is True


def _scenario_execute_resolve_approve(client: Any, sessions_root: Path, repos_root: Path, name: str) -> dict[str, Any]:
    from agent_lab.plan.execute_worktree import create_exec_worktree
    from agent_lab.run.meta import patch_run_meta

    folder = _init_session(sessions_root, name)
    prep_mirrored = _prep_plan_approve(client, folder, name)
    repo = _init_repo(repos_root / name)
    exec_id = f"exec-{name}"
    ew = create_exec_worktree(folder, exec_id=exec_id, git_root=repo, action_key="now:1", session_id=name)
    (ew.worktree_path / "src" / "app.py").write_text("v2 from route cohort\n", encoding="utf-8")
    _commit_all(ew.worktree_path, "route cohort change")
    row = _worktree_execution_row(exec_id=exec_id, ew=ew, status="pending_approval")

    def _seed(run: dict[str, Any]) -> dict[str, Any]:
        run["executions"] = [row]
        return run

    patch_run_meta(folder, _seed)
    response = client.post(
        f"/api/sessions/{name}/execute/resolve",
        json={"execution_id": exec_id, "vote": "approve"},
    )
    body = response.json()
    read_model = _read_model(client, name)
    return {
        "session_id": name,
        "route": "POST /execute/resolve (approve)",
        "prep_plan_approve_mirrored": prep_mirrored,
        "status_code": response.status_code,
        "mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "execution_status": (body.get("execution") or {}).get("status"),
        "merge_committed": bool((body.get("execution") or {}).get("merge", {}).get("commit_sha")),
        "merged_commit_sha_recorded_same_call": read_model.get("state") == "VERIFYING",
        "read_model_migrated": read_model.get("migrated"),
        "read_model_state": read_model.get("state"),
        "note": "bridge 'approve' phase now records the merge commit (RecordMerge) in the "
        "same call once diff-approve lands, so read-model reaches VERIFYING immediately "
        "(merge done, Oracle still pending) instead of trailing at AWAITING_DIFF_DECISION.",
    }


def _scenario_execute_merge_confirm(client: Any, sessions_root: Path, repos_root: Path, name: str) -> dict[str, Any]:
    from agent_lab.plan.execute_worktree import create_exec_worktree
    from agent_lab.run.meta import patch_run_meta

    folder = _init_session(sessions_root, name)
    prep_mirrored = _prep_plan_approve(client, folder, name)
    repo = _init_repo(repos_root / name)
    exec_id = f"exec-{name}"
    ew = create_exec_worktree(folder, exec_id=exec_id, git_root=repo, action_key="now:1", session_id=name)
    (ew.worktree_path / "src" / "app.py").write_text("branch edit\n", encoding="utf-8")
    _commit_all(ew.worktree_path, "branch edit")
    (repo / "src" / "app.py").write_text("main edit\n", encoding="utf-8")
    _commit_all(repo, "main edit")
    row = _worktree_execution_row(exec_id=exec_id, ew=ew, status="pending_approval")

    def _seed(run: dict[str, Any]) -> dict[str, Any]:
        run["executions"] = [row]
        return run

    patch_run_meta(folder, _seed)

    # First attempt goes through the real route: legacy discovers the conflict
    # internally (returns 200, status=merge_conflict) while the bridge's
    # 'approve' phase independently cascades the Mission FSM to
    # AWAITING_DIFF_DECISION, exactly mirroring production behavior.
    first = client.post(
        f"/api/sessions/{name}/execute/resolve",
        json={"execution_id": exec_id, "vote": "approve"},
    )
    first_body = first.json()
    conflict_detected = (first_body.get("execution") or {}).get("status") == "merge_conflict"

    # Human resolves the conflict directly on main.
    (repo / "src" / "app.py").write_text("resolved by human\n", encoding="utf-8")
    _git(repo, "add", "src/app.py")
    _git(repo, "commit", "-m", "resolve conflict")

    response = client.post(f"/api/sessions/{name}/execute/merge/confirm", json={"execution_id": exec_id})
    body = response.json()
    read_model = _read_model(client, name)
    return {
        "session_id": name,
        "route": "POST /execute/merge/confirm",
        "prep_plan_approve_mirrored": prep_mirrored,
        "prep_resolve_status_code": first.status_code,
        "prep_resolve_mirrored": first_body.get("mission_dual_write", {}).get("mirrored"),
        "conflict_detected": conflict_detected,
        "status_code": response.status_code,
        "mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "execution_status": (body.get("execution") or {}).get("status"),
        "read_model_migrated": read_model.get("migrated"),
        "read_model_state": read_model.get("state"),
    }


def _scenario_execute_reverify(client: Any, sessions_root: Path, repos_root: Path, name: str) -> dict[str, Any]:
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import ApproveDiff, MarkDiffReady, StartExecution
    from agent_lab.run.meta import patch_run_meta

    folder = _init_session(sessions_root, name)
    prep_mirrored = _prep_plan_approve(client, folder, name)
    # Advance the Mission bridge to AWAITING_DIFF_DECISION directly via the same
    # repository the routes use (setup for the route under test, not itself the
    # route being measured — mirrors what execute/resolve's bridge would do).
    repo_handle = MissionApplication(folder, "ship widget").repository
    repo_handle.dispatch(StartExecution(), idempotency_key=f"{name}:start:1")
    repo_handle.dispatch(MarkDiffReady(), idempotency_key=f"{name}:diff-ready:1")
    repo_handle.dispatch(ApproveDiff(), idempotency_key=f"{name}:diff-approve:1")

    repo = _init_repo(repos_root / name)
    (repo / "src" / "app.py").write_text("LIVE_OK\n", encoding="utf-8")
    _commit_all(repo, "verify marker")
    head_sha = _git(repo, "rev-parse", "HEAD")
    exec_id = f"exec-{name}"
    execution = {
        "id": exec_id,
        "status": "merged",
        "isolation_effective": "worktree",
        "action_index": 1,
        "action_kind": "now",
        "action_what": "implement widget",
        "action_where": "`src/app.py`",
        "action_verify": "`LIVE_OK`",
        "git_root": str(repo),
        "workspace_root": str(repo),
        "source_touched_paths": ["src/app.py"],
        "touched_paths": ["src/app.py"],
        "verify_retries": 0,
        "verify_history": [],
        "merge": {"status": "merged", "commit_sha": head_sha},
    }

    def _seed(run: dict[str, Any]) -> dict[str, Any]:
        run["executions"] = [execution]
        return run

    patch_run_meta(folder, _seed)
    response = client.post(f"/api/sessions/{name}/execute/reverify", json={"execution_id": exec_id})
    body = response.json()
    read_model = _read_model(client, name)
    return {
        "session_id": name,
        "route": "POST /execute/reverify",
        "prep_plan_approve_mirrored": prep_mirrored,
        "status_code": response.status_code,
        "mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "oracle_verdict": (body.get("execution") or {}).get("oracle", {}).get("verdict"),
        "read_model_migrated": read_model.get("migrated"),
        "read_model_state": read_model.get("state"),
    }


def _scenario_execute_reverify_oracle_fail_repair(
    client: Any, sessions_root: Path, repos_root: Path, name: str
) -> dict[str, Any]:
    """Route-level oracle-fail -> agent repair -> pass, via the real /execute/reverify route.

    Mirrors tests/test_plan_execute_reverify_api.py::test_execute_reverify_endpoint_repairs_oracle_fail,
    with real agent calls swapped for a deterministic monkeypatch (same technique pytest's
    monkeypatch fixture uses — plain setattr/restore — since this is a standalone script).
    """
    import agent_lab.agents.cursor_agent as cursor_agent
    import agent_lab.agents.registry as registry
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import ApproveDiff, MarkDiffReady, StartExecution
    from agent_lab.run.meta import patch_run_meta

    folder = _init_session(sessions_root, name)
    prep_mirrored = _prep_plan_approve(client, folder, name)
    repo_handle = MissionApplication(folder, "ship widget").repository
    repo_handle.dispatch(StartExecution(), idempotency_key=f"{name}:start:1")
    repo_handle.dispatch(MarkDiffReady(), idempotency_key=f"{name}:diff-ready:1")
    repo_handle.dispatch(ApproveDiff(), idempotency_key=f"{name}:diff-approve:1")

    repo = _init_repo(repos_root / name)
    exec_id = f"exec-{name}"
    execution = {
        "id": exec_id,
        "status": "merged",
        "isolation_effective": "worktree",
        "executor": "cursor",
        "action_index": 1,
        "action_kind": "now",
        "action_key": "now:1",
        "action_what": "repair widget",
        "action_where": "`src/app.py`",
        "action_verify": "`REPAIRED_OK`",
        "git_root": str(repo),
        "workspace_root": str(repo),
        "base_branch": "main",
        "base_sha": _git(repo, "rev-parse", "HEAD"),
        "source_touched_paths": ["src/app.py"],
        "expected_paths": ["src/app.py"],
        "verify_retries": 0,
        "oracle": {"verdict": "fail", "detail": "FAIL: missing expected literal(s): REPAIRED_OK"},
        "verify_history": [{"attempt": 0, "status": "failed"}],
    }

    def _seed(run: dict[str, Any]) -> dict[str, Any]:
        run["executions"] = [execution]
        return run

    patch_run_meta(folder, _seed)

    original_available = registry.available_agents
    original_respond = cursor_agent.respond

    def _repair(**kwargs: Any) -> str:
        cwd = Path(kwargs["cwd"])
        (cwd / "src" / "app.py").write_text("LIVE_OK\nREPAIRED_OK\n", encoding="utf-8")
        return "VERIFICATION: PASS — repaired"

    registry.available_agents = lambda: ["cursor"]  # type: ignore[assignment]
    cursor_agent.respond = _repair  # type: ignore[assignment]
    try:
        response = client.post(
            f"/api/sessions/{name}/execute/reverify",
            json={"execution_id": exec_id, "permissions": {"cursor": {"tools": True}}},
        )
    finally:
        registry.available_agents = original_available  # type: ignore[assignment]
        cursor_agent.respond = original_respond  # type: ignore[assignment]

    body = response.json()
    read_model = _read_model(client, name)
    journal_path = folder / ".agent-lab" / "mission-events.jsonl"
    journal_text = journal_path.read_text(encoding="utf-8") if journal_path.is_file() else ""
    repair_event_recorded = "RepairScheduled" in journal_text
    return {
        "session_id": name,
        "route": "POST /execute/reverify (oracle fail -> agent repair -> pass)",
        "prep_plan_approve_mirrored": prep_mirrored,
        "status_code": response.status_code,
        "repair_status": (body.get("repair") or {}).get("status"),
        "repair_agent": (body.get("repair") or {}).get("agent"),
        "final_oracle_verdict": (body.get("execution") or {}).get("oracle", {}).get("verdict"),
        "mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "read_model_migrated": read_model.get("migrated"),
        "read_model_state": read_model.get("state"),
        "repair_event_recorded": repair_event_recorded,
        "note": "the Mission bridge records the intermediate RepairScheduled lifecycle when repair history "
        "contains commit evidence, then records the final Oracle verdict.",
    }


def _scenario_crash_recovery(sessions_root: Path, name: str) -> dict[str, Any]:
    """No HTTP route exists for ActivityQueue crash/restart — the scheduler daemon owns this
    state machine entirely in-process (see start_mission_scheduler_background). Evidence here
    is at the persistence layer: a claimed+committed activity survives a simulated process
    restart (fresh ActivityQueue instance reading the same on-disk queue file) and completes.
    """
    from agent_lab.mission.activity_queue import ActivityQueue, QueueState, QueuedActivity
    from agent_lab.mission.recovery import RecoveryAction, SideEffectState

    folder = sessions_root / name
    folder.mkdir(parents=True)
    queue = ActivityQueue.for_session(folder)
    activity = QueuedActivity(f"activity-{name}", name, "execute", 1, "crash-key")
    queue.enqueue(activity)
    claimed = queue.claim_next("worker-a", now=10.0, ttl_s=5.0)
    if claimed is None:
        raise RuntimeError("activity was not claimed")
    queue.record_side_effect(activity.activity_id, "worker-a", claimed.lease.token, SideEffectState.COMMITTED)

    # Simulate the daemon process crashing after commit but before completion: a brand-new
    # ActivityQueue reading the same on-disk file stands in for the post-restart process.
    restarted = ActivityQueue.for_session(folder)
    decisions = restarted.recover(now=15.0)
    completed = ActivityQueue.for_session(folder).snapshot()

    return {
        "session_id": name,
        "route": "(no HTTP route — scheduler daemon in-process recovery)",
        "recovery_action": decisions[0].action.value if decisions else None,
        "recovered_and_completed": bool(decisions) and decisions[0].action is RecoveryAction.COMPLETE and any(
            item.state is QueueState.COMPLETED for item in completed
        ),
    }


def _rollback_fresh_session_legacy_only(client: Any, sessions_root: Path, name: str) -> dict[str, Any]:
    """Flag OFF: a brand-new session must succeed with zero Mission side effects."""
    from agent_lab.plan.workflow_state import set_plan_workflow_phase

    folder = _init_session(sessions_root, name)
    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    response = client.post(f"/api/sessions/{name}/plan/approve", json={"goal": "rollback check"})
    body = response.json()
    return {
        "session_id": name,
        "route": "POST /plan/approve (flag OFF, fresh session)",
        "status_code": response.status_code,
        "dual_write_enabled_flag": body.get("mission_dual_write", {}).get("enabled"),
        "mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "plan_workflow_phase": body.get("plan_workflow", {}).get("phase"),
        "journal_created": _journal_exists(folder),
    }


def _rollback_existing_mirrored_session_stays_legacy(client: Any, sessions_root: Path, name: str) -> dict[str, Any]:
    """Flag OFF: a session already mirrored by the cohort must keep working via legacy only."""
    folder = sessions_root / name
    before = _read_model(client, name)
    from agent_lab.human_inbox import create_inbox_item

    item = create_inbox_item(folder, kind="question", source="dual-write-route-cohort-rollback", prompt="Any more?")
    response = client.post(f"/api/sessions/{name}/inbox/{item['id']}/resolve", json={"decision": "go"})
    body = response.json()
    after = _read_model(client, name)
    return {
        "session_id": name,
        "route": "POST /inbox/{item}/resolve (flag OFF, previously-migrated session)",
        "status_code": response.status_code,
        "dual_write_enabled_flag": body.get("mission_dual_write", {}).get("enabled"),
        "mirrored": body.get("mission_dual_write", {}).get("mirrored"),
        "legacy_inbox_resolved": body.get("ok"),
        "read_model_unchanged": before.get("event_cursor") == after.get("event_cursor"),
    }


def run_cohort(sessions_root: Path, repos_root: Path, *, prefix: str = "dualwrite-route") -> dict[str, Any]:
    sessions_root.mkdir(parents=True, exist_ok=True)
    repos_root.mkdir(parents=True, exist_ok=True)
    prefix = prefix.strip() or "dualwrite-route"

    os.environ["AGENT_LAB_MISSION_DUAL_WRITE"] = "1"
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
    client = _client(sessions_root)

    rows: list[dict[str, Any]] = []
    rows.append(_scenario_plan_approve(client, sessions_root, f"{prefix}-01-plan-approve"))
    rows.append(_scenario_plan_approve(client, sessions_root, f"{prefix}-02-plan-approve"))
    rows.append(_scenario_plan_reject(client, sessions_root, f"{prefix}-03-plan-reject"))
    rows.append(_scenario_plan_reject(client, sessions_root, f"{prefix}-04-plan-reject"))
    rows.append(_scenario_inbox_resolve(client, sessions_root, f"{prefix}-05-inbox-resolve"))
    rows.append(_scenario_inbox_resolve(client, sessions_root, f"{prefix}-06-inbox-resolve"))
    rows.append(_scenario_execute_resolve_approve(client, sessions_root, repos_root, f"{prefix}-07-execute-resolve"))
    rows.append(_scenario_execute_resolve_approve(client, sessions_root, repos_root, f"{prefix}-08-execute-resolve"))
    rows.append(_scenario_execute_merge_confirm(client, sessions_root, repos_root, f"{prefix}-09-merge-confirm"))
    rows.append(_scenario_execute_reverify(client, sessions_root, repos_root, f"{prefix}-10-reverify"))

    cohort_parity_pass = all(
        row["status_code"] == 200 and row["mirrored"] is True and row["read_model_migrated"] is True for row in rows
    )

    extended_rows: list[dict[str, Any]] = []
    extended_rows.append(
        _scenario_execute_reverify_oracle_fail_repair(client, sessions_root, repos_root, f"{prefix}-11-fail-repair")
    )
    extended_rows.append(_scenario_crash_recovery(sessions_root, f"{prefix}-12-crash-recovery"))
    extended_pass = (
        extended_rows[0]["status_code"] == 200
        and extended_rows[0]["repair_status"] == "merged"
        and extended_rows[0]["final_oracle_verdict"] == "pass"
        and extended_rows[0]["mirrored"] is True
        and extended_rows[0]["repair_event_recorded"] is True
        and extended_rows[1]["recovered_and_completed"] is True
    )

    # Rollback: flip the flag off and prove (a) fresh sessions stay legacy-only,
    # (b) sessions already mirrored by the cohort keep working via legacy alone.
    del os.environ["AGENT_LAB_MISSION_DUAL_WRITE"]
    rollback_rows: list[dict[str, Any]] = []
    rollback_rows.append(_rollback_fresh_session_legacy_only(client, sessions_root, f"{prefix}-rb-01-fresh"))
    rollback_rows.append(
        _rollback_existing_mirrored_session_stays_legacy(client, sessions_root, f"{prefix}-01-plan-approve")
    )
    rollback_pass = (
        rollback_rows[0]["status_code"] == 200
        and rollback_rows[0]["dual_write_enabled_flag"] is False
        and rollback_rows[0]["mirrored"] is False
        and rollback_rows[0]["journal_created"] is False
        and rollback_rows[1]["status_code"] == 200
        and rollback_rows[1]["dual_write_enabled_flag"] is False
        and rollback_rows[1]["mirrored"] is False
        and rollback_rows[1]["legacy_inbox_resolved"] is True
    )

    return {
        "sessions_root": str(sessions_root),
        "route_count": len(rows),
        "cohort_parity_pass": cohort_parity_pass,
        "rollback_pass": rollback_pass,
        "extended_pass": extended_pass,
        "sessions": rows,
        "extended": extended_rows,
        "rollback": rollback_rows,
        "created_session_dirs": sorted(p.name for p in sessions_root.glob(f"{prefix}*")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True, help="target sessions directory (may be the real operational one)")
    parser.add_argument("--repos", type=Path, required=True, help="scratch directory for the git repos used by execute scenarios (kept outside --sessions)")
    args = parser.parse_args()
    report = run_cohort(args.sessions, args.repos)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["cohort_parity_pass"] and report["rollback_pass"] and report["extended_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
