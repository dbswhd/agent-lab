"""Human cutover 판정용: 실제 API 프로세스 kill -> restart recovery 증거.

이전 evidence(scripts/mission_dual_write_route_cohort.py의 crash-recovery 시나리오)는
"새 ActivityQueue 인스턴스가 같은 디스크 파일을 읽는다"로 재시작을 시뮬레이션했다. 이
스크립트는 진짜 별도 uvicorn 서브프로세스를 띄우고 SIGKILL로 강제 종료한 뒤, 완전히 새
프로세스(새 PID)를 같은 --sessions 디렉터리로 재기동해 다음을 실제 네트워크 HTTP로 검증한다.

1) G3 crash-recovery (``agent_lab.crash_recovery.reconcile_crashed_merges``) — 매 부팅마다
   자동 실행되는 기존 메커니즘. merge가 git에는 랜딩됐지만 run.json에 "merged"가 기록되기
   *전에* 죽은 상황을 실제로 재현하고(checkpoint를 손으로 arm), 재기동한 새 프로세스가
   부팅 스캔만으로 그 세션을 ``merged``로 reconcile하는지 ``/api/health/daemon`` +
   run.json으로 확인한다.
2) Mission journal replay — dual-write로 만든 세션이 진짜 kill/restart 이후에도
   ``/mission/read-model``에서 동일한 상태를 반환하는지 확인한다(파일 레벨이 아니라
   진짜 새 프로세스가 새 소켓으로 응답).
3) ActivityQueue 참고 확인 — ``ActivityQueue.recover()``는 부팅 경로 어디에도 자동으로
   연결돼 있지 않다는 사실을 실측한다(커밋된 side effect가 재기동만으로는 COMPLETED로
   바뀌지 않음, 수동 호출 시에는 정상 동작).

대상 sessions 디렉터리는 실제 운영 sessions/를 가리킬 수 있다. 시작 전 살아있는
``checkpoint.phase == "merging"`` row가 있는 기존 세션이 있는지 먼저 스캔해 사고를
방지한다(있으면 즉시 중단).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SAMPLE_PLAN = """# Process kill/restart recovery demo

## 지금 실행

1. Add marker
   - 무엇을: implement marker
   - 어디서: `src/marker.py`
   - 검증: `pytest tests/test_marker.py`
"""


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check)
    return result.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    (path / "src").mkdir()
    (path / "src" / "marker.py").write_text("v1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def _preflight_no_live_checkpoints(sessions_root: Path) -> None:
    """Abort loudly rather than silently reconcile a real user's unrelated crash state."""
    hits: list[str] = []
    for folder in sorted(sessions_root.iterdir()):
        if not folder.is_dir() or folder.name.startswith((".", "_")):
            continue
        run_path = folder / "run.json"
        if not run_path.is_file():
            continue
        try:
            run = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in run.get("executions") or []:
            if isinstance(row, dict):
                cp = row.get("checkpoint")
                if isinstance(cp, dict) and cp.get("phase") == "merging":
                    hits.append(folder.name)
    if hits:
        raise RuntimeError(
            f"refusing to run: {len(hits)} existing session(s) already have a live merge "
            f"checkpoint (would be reconciled by this run's boot scan too): {hits[:5]}"
        )


def _wait_for_health(base_url: str, *, timeout_s: float = 30.0) -> bool:
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=2) as resp:  # noqa: S310
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.5)
    return False


def _wait_for_port_closed(base_url: str, *, timeout_s: float = 15.0) -> bool:
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base_url}/api/health", timeout=1)  # noqa: S310
            time.sleep(0.3)
        except (urllib.error.URLError, ConnectionError, OSError):
            return True
    return False


def _http_json(
    method: str, url: str, *, json_body: dict[str, Any] | None = None, timeout: float = 20.0
) -> tuple[int, dict[str, Any]]:
    import urllib.request
    import urllib.error

    data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"detail": str(exc)}
        return exc.code, body


def _start_server(
    *, port: int, sessions_dir: Path, config_dir: Path, daemon_state_path: Path, log_path: Path
) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(
        {
            "AGENT_LAB_MOCK_AGENTS": "1",
            "AGENT_LAB_MISSION_DUAL_WRITE": "1",
            "AGENT_LAB_CRASH_RECOVERY": "1",
            "AGENT_LAB_MISSION_SCHEDULER": "1",
            "AGENT_LAB_SESSIONS_DIR": str(sessions_dir),
            "AGENT_LAB_CONFIG_DIR": str(config_dir),
            "AGENT_LAB_DAEMON_STATE": str(daemon_state_path),
        }
    )
    log_file = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(  # noqa: S603
        [str(ROOT / ".venv" / "bin" / "uvicorn"), "app.server.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return proc


def run_evidence(sessions_root: Path, repos_root: Path, *, port: int) -> dict[str, Any]:
    sessions_root.mkdir(parents=True, exist_ok=True)
    repos_root.mkdir(parents=True, exist_ok=True)
    _preflight_no_live_checkpoints(sessions_root)

    base_url = f"http://127.0.0.1:{port}"
    session_name = "dualwrite-crash-01-process-restart"
    folder = sessions_root / session_name
    folder.mkdir(parents=True)
    (folder / "topic.txt").write_text(session_name, encoding="utf-8")
    (folder / "chat.jsonl").write_text("", encoding="utf-8")
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text(json.dumps({"topic": session_name}), encoding="utf-8")
    from agent_lab.plan.workflow_state import set_plan_workflow_phase

    set_plan_workflow_phase(folder, "HUMAN_PENDING")

    activity_session_name = "dualwrite-crash-02-activity-queue"
    activity_folder = sessions_root / activity_session_name
    activity_folder.mkdir(parents=True)

    config_dir = Path(tempfile.mkdtemp(prefix="dualwrite-crash-config-"))
    daemon_state_path = Path(tempfile.mkdtemp(prefix="dualwrite-crash-daemon-")) / "daemon_state.json"
    log_path = Path(tempfile.mkdtemp(prefix="dualwrite-crash-logs-")) / "server.log"

    result: dict[str, Any] = {"session_id": session_name, "port": port}

    proc_a = _start_server(
        port=port,
        sessions_dir=sessions_root,
        config_dir=config_dir,
        daemon_state_path=daemon_state_path,
        log_path=log_path,
    )
    try:
        healthy = _wait_for_health(base_url)
        result["process_a"] = {"pid": proc_a.pid, "healthy": healthy}
        if not healthy:
            raise RuntimeError(f"process A never became healthy; see {log_path}")

        status, body = _http_json(
            "POST", f"{base_url}/api/sessions/{session_name}/plan/approve", json_body={"goal": "kill/restart demo"}
        )
        result["plan_approve_before_kill"] = {
            "status_code": status,
            "mirrored": body.get("mission_dual_write", {}).get("mirrored"),
            "plan_workflow_phase": body.get("plan_workflow", {}).get("phase"),
        }

        # --- Build the exact crash window `_arm_merge_checkpoint` targets: the exec
        # branch has *actually landed* on base via a real `git merge`, but run.json
        # still says pending_approval with a live checkpoint — as if the process died
        # between the merge succeeding and the status-flip persist.
        from agent_lab.plan.execute_worktree import create_exec_worktree
        from agent_lab.run.meta import patch_run_meta

        repo = _init_repo(repos_root / session_name)
        base_sha_before = _git(repo, "rev-parse", "HEAD")
        exec_id = f"exec-{session_name}"
        ew = create_exec_worktree(folder, exec_id=exec_id, git_root=repo, action_key="now:1", session_id=session_name)
        (ew.worktree_path / "src" / "marker.py").write_text("v2 crash-recovery demo\n", encoding="utf-8")
        _git(ew.worktree_path, "add", "-A")
        _git(ew.worktree_path, "commit", "-m", "exec change")
        exec_commit_sha = _git(ew.worktree_path, "rev-parse", "HEAD")
        _git(repo, "merge", "--no-ff", ew.branch, "-m", "agent-lab: crash-window merge")
        base_head_after_merge = _git(repo, "rev-parse", "HEAD")

        checkpoint = {
            "phase": "merging",
            "op": "merge",
            "started_at": "2026-07-13T00:00:00Z",
            "git_root": str(repo),
            "worktree_path": str(ew.worktree_path),
            "base_branch": ew.base_branch,
            "base_sha_before": base_sha_before,
            "exec_branch": ew.branch,
            "exec_commit_sha": exec_commit_sha,
            "prev_status": "pending_approval",
            "prev_merge": {},
            "snapshot_id": exec_id,
        }
        row = {
            "id": exec_id,
            "status": "pending_approval",
            "isolation_effective": "worktree",
            "action_index": 1,
            "action_kind": "now",
            "action_what": "implement marker",
            "action_where": "`src/marker.py`",
            "action_verify": "`pytest tests/test_marker.py`",
            "checkpoint": checkpoint,
            **ew.to_dict(),
        }

        def _seed(run: dict[str, Any]) -> dict[str, Any]:
            run["executions"] = [row]
            return run

        patch_run_meta(folder, _seed)
        result["crash_window_fixture"] = {
            "base_sha_before": base_sha_before,
            "exec_commit_sha": exec_commit_sha,
            "base_head_after_merge": base_head_after_merge,
            "note": "git merge landed for real; run.json still says pending_approval with a live checkpoint — the exact pre-crash window.",
        }

        # --- ActivityQueue: enqueue + claim + commit a side effect that process A never completes.
        from agent_lab.mission.activity_queue import ActivityQueue, QueuedActivity
        from agent_lab.mission.recovery import SideEffectState

        queue = ActivityQueue.for_session(activity_folder)
        activity = QueuedActivity("activity-crash-demo", activity_session_name, "execute", 1, "crash-key")
        queue.enqueue(activity)
        claimed = queue.claim_next("worker-a", now=10.0, ttl_s=5.0)
        if claimed is None:
            raise RuntimeError("activity was not claimed")
        queue.record_side_effect(activity.activity_id, "worker-a", claimed.lease.token, SideEffectState.COMMITTED)

        pre_kill_read_model_status, pre_kill_read_model = _http_json(
            "GET", f"{base_url}/api/sessions/{session_name}/mission/read-model"
        )
        result["read_model_before_kill"] = {
            "status_code": pre_kill_read_model_status,
            "state": pre_kill_read_model.get("state"),
            "migrated": pre_kill_read_model.get("migrated"),
        }

        # --- Real, ungraceful crash: SIGKILL, not terminate().
        pid_a = proc_a.pid
        os.kill(pid_a, signal.SIGKILL)
        proc_a.wait(timeout=10)
        port_closed = _wait_for_port_closed(base_url)
        try:
            os.kill(pid_a, 0)
            process_a_gone = False
        except ProcessLookupError:
            process_a_gone = True
        result["kill"] = {"pid": pid_a, "port_closed_after_kill": port_closed, "process_confirmed_gone": process_a_gone}
    finally:
        if proc_a.poll() is None:
            try:
                os.kill(proc_a.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc_a.wait(timeout=10)

    # --- Fresh process, new PID, same sessions dir and daemon-state path.
    proc_b = _start_server(
        port=port,
        sessions_dir=sessions_root,
        config_dir=config_dir,
        daemon_state_path=daemon_state_path,
        log_path=log_path,
    )
    try:
        healthy_b = _wait_for_health(base_url)
        result["process_b"] = {
            "pid": proc_b.pid,
            "healthy": healthy_b,
            "different_pid_than_a": proc_b.pid != result["kill"]["pid"],
        }
        if not healthy_b:
            raise RuntimeError(f"process B never became healthy; see {log_path}")

        status, daemon_payload = _http_json("GET", f"{base_url}/api/health/daemon")
        result["daemon_health_after_restart"] = {
            "status_code": status,
            "pid": daemon_payload.get("pid"),
            "last_recovery_result": daemon_payload.get("last_recovery_result") or daemon_payload.get("last_recovery"),
            "raw_keys": sorted(daemon_payload.keys()),
        }

        run_after = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        recon_row = next((r for r in run_after.get("executions") or [] if r.get("id") == exec_id), {})
        result["g3_crash_recovery_outcome"] = {
            "status": recon_row.get("status"),
            "merge_status": (recon_row.get("merge") or {}).get("status"),
            "merge_commit_sha": (recon_row.get("merge") or {}).get("commit_sha"),
            "merge_recovered_flag": (recon_row.get("merge") or {}).get("recovered"),
            "checkpoint_cleared": "checkpoint" not in recon_row,
            "recovery_record": recon_row.get("recovery"),
            "matches_git_ground_truth": (recon_row.get("merge") or {}).get("commit_sha") == base_head_after_merge,
        }

        status, read_model_after = _http_json("GET", f"{base_url}/api/sessions/{session_name}/mission/read-model")
        result["read_model_after_restart"] = {
            "status_code": status,
            "state": read_model_after.get("state"),
            "migrated": read_model_after.get("migrated"),
            "matches_before_kill": read_model_after.get("state") == pre_kill_read_model.get("state")
            and read_model_after.get("migrated") == pre_kill_read_model.get("migrated"),
        }

        # Distinct route (not plan/approve again — the plan is already APPROVED, so
        # re-approving would 409) to prove process B serves production routes normally.
        status, tick_body = _http_json("POST", f"{base_url}/api/mission-scheduler/tick?force=true", json_body={})
        result["route_continues_after_restart"] = {"status_code": status, "ok": tick_body.get("ok")}

        # --- ActivityQueue: confirm recovery is NOT automatic on restart (no code path
        # calls .recover() at boot or on scheduler tick), then confirm the mechanism
        # itself still works when invoked explicitly.
        queue_after_restart = ActivityQueue.for_session(activity_folder)
        snapshot_after_restart = queue_after_restart.snapshot()
        still_not_completed = all(item.state.value != "completed" for item in snapshot_after_restart)
        decisions = queue_after_restart.recover(now=9999.0)
        snapshot_after_manual_recover = ActivityQueue.for_session(activity_folder).snapshot()
        manually_recovered = any(item.state.value == "completed" for item in snapshot_after_manual_recover)
        result["activity_queue_recovery"] = {
            "auto_recovered_by_process_restart_alone": not still_not_completed,
            "recovered_after_explicit_recover_call": manually_recovered,
            "recovery_action_when_invoked": decisions[0].action.value if decisions else None,
            "note": "no code path in _api_startup or scheduler_tick calls ActivityQueue.recover() automatically; it must be invoked explicitly.",
        }
    finally:
        if proc_b.poll() is None:
            os.kill(proc_b.pid, signal.SIGTERM)
            try:
                proc_b.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.kill(proc_b.pid, signal.SIGKILL)
                proc_b.wait(timeout=10)

    result["log_path"] = str(log_path)
    result["overall_pass"] = (
        result["process_a"]["healthy"]
        and result["plan_approve_before_kill"]["status_code"] == 200
        and result["plan_approve_before_kill"]["mirrored"] is True
        and result["kill"]["process_confirmed_gone"]
        and result["process_b"]["healthy"]
        and result["process_b"]["different_pid_than_a"]
        and result["g3_crash_recovery_outcome"]["status"] == "merged"
        and result["g3_crash_recovery_outcome"]["matches_git_ground_truth"]
        and result["g3_crash_recovery_outcome"]["checkpoint_cleared"]
        and result["read_model_after_restart"]["matches_before_kill"]
        and result["route_continues_after_restart"]["status_code"] == 200
        and result["route_continues_after_restart"]["ok"] is True
        and result["activity_queue_recovery"]["recovered_after_explicit_recover_call"] is True
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--repos", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8891)
    args = parser.parse_args()
    report = run_evidence(args.sessions, args.repos, port=args.port)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("overall_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
