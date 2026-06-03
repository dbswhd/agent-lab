"""One-shot live Cursor SDK dry-run in an isolated git worktree (M0 Go/No-Go)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.plan_actions import find_dry_run_action
from agent_lab.plan_execute import resolve_execution, run_dry_run
from agent_lab.plan_execute_git import detect_git_root
from agent_lab.plan_pending import PlanSnapshotRequired, approve_pending_plan

SPIKE_MARKER = "LIVE_M0_OK"
SPIKE_REL_PATH = "src/spike.txt"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def _git_porcelain(cwd: Path) -> str:
    return _git(cwd, "status", "--porcelain")


def _init_spike_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / SPIKE_REL_PATH).write_text("# baseline\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "live spike init")


def _plan_md(repo: Path) -> str:
    rel = SPIKE_REL_PATH
    return f"""## 지금 실행
1.
   - 무엇을: Add one line `{SPIKE_MARKER}` to {rel} (minimal live M0 check).
   - 어디서: `{rel}`
   - 검증: `{rel}` contains `{SPIKE_MARKER}`
"""


def _seed_plan_snapshot(session: Path, plan_md: str) -> None:
    action = find_dry_run_action(plan_md, 1, kind="now")
    if action is None:
        raise ValueError("plan action 1 not found")
    from agent_lab.plan_pending import ensure_plan_snapshot_approved

    try:
        ensure_plan_snapshot_approved(session, action, plan_md)
    except PlanSnapshotRequired as exc:
        approve_pending_plan(session, exc.pending_plan["id"])


def _preflight_cursor() -> dict[str, Any]:
    from agent_lab.agent_preflight import agent_preflight_row
    from agent_lab.agents.cursor_agent import is_available

    row = agent_preflight_row("cursor", probe_bridge=True, probe_cli=False)
    return {
        "sdk_available": is_available(),
        "ready": row.get("ready"),
        "degraded": row.get("degraded"),
        "failure_code": row.get("failure_code"),
        "reason": row.get("reason"),
        "bridge_mode": row.get("bridge_mode"),
    }


def run_live_worktree_spike(
    *,
    work_parent: Path | None = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    """
    Run a real Cursor dry-run against a disposable git repo + worktree.

    Requires CURSOR_API_KEY, cursor-sdk, and a reachable bridge.
    Never logs secrets.
    """
    from agent_lab.agents.cursor_agent import is_available

    report: dict[str, Any] = {
        "kind": "live_cursor_worktree_dry_run",
        "started_at": _now(),
        "status": "skipped",
        "checks": {},
        "preflight": {},
        "execution": None,
        "errors": [],
    }

    if os.getenv("AGENT_LAB_SKIP_LIVE", "").strip() in {"1", "true", "yes"}:
        report["errors"].append("AGENT_LAB_SKIP_LIVE set")
        report["finished_at"] = _now()
        return report

    preflight = _preflight_cursor()
    report["preflight"] = preflight
    if not is_available():
        report["errors"].append("Cursor executor unavailable (CURSOR_API_KEY / cursor-sdk)")
        report["finished_at"] = _now()
        return report
    if preflight.get("ready") is not True:
        report["errors"].append(
            preflight.get("reason")
            or preflight.get("failure_code")
            or "cursor preflight not ready"
        )
        report["finished_at"] = _now()
        return report

    parent = work_parent or Path(tempfile.mkdtemp(prefix="agent-lab-live-m0-"))
    owns_parent = work_parent is None
    repo = parent / "repo"
    session = parent / "session"
    session.mkdir(parents=True, exist_ok=True)
    (session / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room",
                "run_schema_version": 1,
                "topic": "live M0 worktree spike",
                "created_at": _now(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        _init_spike_repo(repo)
        plan_md = _plan_md(repo)
        (session / "plan.md").write_text(plan_md, encoding="utf-8")
        _seed_plan_snapshot(session, plan_md)

        main_before = _git_porcelain(repo)
        permissions = {"_discuss_cwd": str(repo.resolve())}

        execution = run_dry_run(
            session,
            action_index=1,
            permissions=permissions,
        )
        report["execution"] = {
            "id": execution.get("id"),
            "status": execution.get("status"),
            "isolation_effective": execution.get("isolation_effective"),
            "worktree_path": execution.get("worktree_path"),
            "git_root": execution.get("git_root"),
            "exec_branch": execution.get("exec_branch"),
            "workspace_root": execution.get("workspace_root"),
        }

        worktree_path = Path(str(execution.get("worktree_path") or ""))
        git_root = Path(str(execution.get("git_root") or repo))
        main_after = _git_porcelain(git_root)

        cwd_ok = False
        if worktree_path.is_dir():
            detected = detect_git_root(worktree_path)
            cwd_ok = detected == worktree_path.resolve()

        checks = {
            "isolation_worktree": execution.get("isolation_effective") == "worktree",
            "pending_approval": execution.get("status") == "pending_approval",
            "main_clean_before": main_before == "",
            "main_clean_after_dry_run": main_after == "",
            "worktree_exists": worktree_path.is_dir(),
            "cwd_is_worktree_root": cwd_ok,
            "git_root_matches_repo": str(git_root.resolve()) == str(repo.resolve()),
        }
        report["checks"] = checks

        if execution.get("status") == "pending_approval":
            resolve_execution(
                session,
                execution_id=str(execution["id"]),
                vote="reject",
                permissions=permissions,
            )
            checks["worktree_removed_after_reject"] = not worktree_path.exists()
            checks["main_clean_after_reject"] = _git_porcelain(git_root) == ""

        failed = [k for k, v in checks.items() if not v]
        report["status"] = "go" if not failed else "no_go"
        if failed:
            report["errors"].append(f"failed checks: {', '.join(failed)}")
    except Exception as exc:  # noqa: BLE001 — surface as report for operators
        report["status"] = "no_go"
        report["errors"].append(str(exc))
    finally:
        report["finished_at"] = _now()
        if cleanup and owns_parent and parent.exists():
            shutil.rmtree(parent, ignore_errors=True)

    return report


def run_live_worktree_merge_spike(
    *,
    work_parent: Path | None = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    """
    Run a real Cursor dry-run, then approve it into the disposable base branch.

    This is Tier C operator coverage: it never targets the agent-lab repo and
    keeps all merge state inside a temporary git repository.
    """
    from agent_lab.agents.cursor_agent import is_available

    report: dict[str, Any] = {
        "kind": "live_cursor_worktree_merge",
        "started_at": _now(),
        "status": "skipped",
        "checks": {},
        "preflight": {},
        "execution": None,
        "merge": None,
        "rollback": {},
        "errors": [],
    }

    if os.getenv("AGENT_LAB_SKIP_LIVE", "").strip() in {"1", "true", "yes"}:
        report["errors"].append("AGENT_LAB_SKIP_LIVE set")
        report["finished_at"] = _now()
        return report

    preflight = _preflight_cursor()
    report["preflight"] = preflight
    if not is_available():
        report["errors"].append("Cursor executor unavailable (CURSOR_API_KEY / cursor-sdk)")
        report["finished_at"] = _now()
        return report
    if preflight.get("ready") is not True:
        report["errors"].append(
            preflight.get("reason")
            or preflight.get("failure_code")
            or "cursor preflight not ready"
        )
        report["finished_at"] = _now()
        return report

    parent = work_parent or Path(tempfile.mkdtemp(prefix="agent-lab-live-merge-"))
    owns_parent = work_parent is None
    repo = parent / "repo"
    session = parent / "session"
    session.mkdir(parents=True, exist_ok=True)
    (session / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room",
                "run_schema_version": 1,
                "topic": "live worktree merge spike",
                "created_at": _now(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        _init_spike_repo(repo)
        plan_md = _plan_md(repo)
        (session / "plan.md").write_text(plan_md, encoding="utf-8")
        _seed_plan_snapshot(session, plan_md)

        pre_merge_sha = _git(repo, "rev-parse", "HEAD")
        main_before = _git_porcelain(repo)
        permissions = {"_discuss_cwd": str(repo.resolve())}

        execution = run_dry_run(
            session,
            action_index=1,
            permissions=permissions,
        )
        report["execution"] = {
            "id": execution.get("id"),
            "status": execution.get("status"),
            "isolation_effective": execution.get("isolation_effective"),
            "worktree_path": execution.get("worktree_path"),
            "git_root": execution.get("git_root"),
            "exec_branch": execution.get("exec_branch"),
            "exec_commit_sha": execution.get("exec_commit_sha"),
            "workspace_root": execution.get("workspace_root"),
        }

        worktree_path = Path(str(execution.get("worktree_path") or ""))
        git_root = Path(str(execution.get("git_root") or repo))
        main_after_dry_run = _git_porcelain(git_root)
        cwd_ok = False
        if worktree_path.is_dir():
            detected = detect_git_root(worktree_path)
            cwd_ok = detected == worktree_path.resolve()

        checks = {
            "main_clean_before": main_before == "",
            "isolation_worktree": execution.get("isolation_effective") == "worktree",
            "pending_approval": execution.get("status") == "pending_approval",
            "main_clean_after_dry_run": main_after_dry_run == "",
            "worktree_exists_after_dry_run": worktree_path.is_dir(),
            "cwd_is_worktree_root": cwd_ok,
            "git_root_matches_repo": str(git_root.resolve()) == str(repo.resolve()),
        }
        report["checks"] = checks

        if execution.get("status") == "pending_approval":
            approval = resolve_execution(
                session,
                execution_id=str(execution["id"]),
                vote="approve",
                permissions=permissions,
            )
            merged_execution = approval.get("execution") or {}
            merge = dict(merged_execution.get("merge") or {})
            report["merge"] = {
                "status": merge.get("status"),
                "commit_sha": merge.get("commit_sha"),
                "conflict_files": merge.get("conflict_files") or [],
                "execution_status": merged_execution.get("status"),
            }
            merge_commit_sha = str(merge.get("commit_sha") or "")
            branch = str(execution.get("exec_branch") or "")
            branch_list = _git(git_root, "branch", "--list", branch) if branch else ""
            base_text = (repo / SPIKE_REL_PATH).read_text(encoding="utf-8")
            head_sha = _git(git_root, "rev-parse", "HEAD")

            checks.update(
                {
                    "approve_status_merged": merged_execution.get("status") == "merged",
                    "merge_commit_sha_present": bool(merge_commit_sha),
                    "head_is_merge_commit": bool(merge_commit_sha)
                    and head_sha == merge_commit_sha,
                    "base_head_changed": head_sha != pre_merge_sha,
                    "base_branch_contains_marker": SPIKE_MARKER in base_text,
                    "main_clean_after_merge": _git_porcelain(git_root) == "",
                    "worktree_removed_after_merge": not worktree_path.exists(),
                    "exec_branch_removed_after_merge": branch_list.strip() == "",
                }
            )
            report["rollback"] = {
                "repo": str(repo.resolve()),
                "pre_merge_sha": pre_merge_sha,
                "reset_command": f"git -C {repo.resolve()} reset --hard {pre_merge_sha}",
            }

        failed = [k for k, v in checks.items() if not v]
        report["status"] = "go" if not failed else "no_go"
        if failed:
            report["errors"].append(f"failed checks: {', '.join(failed)}")
    except Exception as exc:  # noqa: BLE001 — surface as report for operators
        report["status"] = "no_go"
        report["errors"].append(str(exc))
    finally:
        report["finished_at"] = _now()
        if cleanup and owns_parent and parent.exists():
            shutil.rmtree(parent, ignore_errors=True)

    return report


def format_report_lines(report: dict[str, Any]) -> list[str]:
    label = "Live Cursor worktree dry-run"
    if report.get("kind") == "live_cursor_worktree_merge":
        label = "Live Cursor worktree merge"
    lines = [
        f"{label}: {report.get('status', 'unknown').upper()}",
        f"  preflight ready: {report.get('preflight', {}).get('ready')}",
        f"  bridge_mode: {report.get('preflight', {}).get('bridge_mode')}",
    ]
    checks = report.get("checks") or {}
    for key, ok in sorted(checks.items()):
        lines.append(f"  {key}: {'OK' if ok else 'FAIL'}")
    for err in report.get("errors") or []:
        lines.append(f"  error: {err}")
    if report.get("execution"):
        ex = report["execution"]
        lines.append(f"  execution: {ex.get('id')} ({ex.get('status')})")
    if report.get("merge"):
        merge = report["merge"]
        lines.append(
            f"  merge: {merge.get('status')} ({str(merge.get('commit_sha') or '')[:12]})"
        )
    return lines
