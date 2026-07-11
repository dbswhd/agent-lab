"""Merge Checks SSOT — Conductor Checks tab (MB-5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.core.execution_status_scopes import (
    OPEN_MERGE_PENDING_STATUSES as OPEN_PENDING_STATUSES,
    PENDING_STATUS,
    find_open_merge_pending_execution,
)


def _worktree_hooks_check(execution: dict[str, Any] | None) -> dict[str, Any]:
    if execution is None:
        return {"id": "worktree_hooks", "ok": True, "detail": "n/a"}
    if str(execution.get("isolation_effective") or "") != "worktree":
        return {"id": "worktree_hooks", "ok": True, "detail": "not worktree"}
    hooks = execution.get("worktree_hooks")
    if not isinstance(hooks, dict):
        from agent_lab.worktree_hooks import find_worktree_hooks

        git_root = execution.get("git_root")
        config = find_worktree_hooks(Path(str(git_root)) if git_root else None)
        if config and config.verify:
            return {
                "id": "worktree_hooks",
                "ok": False,
                "detail": "verify hooks not run",
            }
        return {"id": "worktree_hooks", "ok": True, "detail": "no hooks configured"}
    create = hooks.get("create")
    if isinstance(create, dict) and not create.get("ok"):
        return {"id": "worktree_hooks", "ok": False, "detail": "create failed"}
    setup = hooks.get("setup")
    if isinstance(setup, dict) and not setup.get("ok"):
        return {"id": "worktree_hooks", "ok": False, "detail": "setup failed"}
    verify = hooks.get("verify")
    if verify is None:
        config_verify: list[str] = []
        for source in (setup, create, hooks.get("config_summary")):
            if not isinstance(source, dict):
                continue
            raw_config = source.get("config") if "config" in source else None
            if isinstance(raw_config, dict) and raw_config.get("verify"):
                config_verify = list(raw_config.get("verify") or [])
                break
            if source.get("has_verify"):
                config_verify = ["configured"]
                break
        if config_verify:
            return {"id": "worktree_hooks", "ok": False, "detail": "verify pending"}
        return {"id": "worktree_hooks", "ok": True, "detail": "verify not configured"}
    if not verify.get("ok"):
        return {"id": "worktree_hooks", "ok": False, "detail": "verify failed"}
    return {"id": "worktree_hooks", "ok": True, "detail": "ok"}


def _worktree_check(execution: dict[str, Any] | None) -> dict[str, Any]:
    if execution is None:
        return {"id": "git_worktree", "ok": True, "detail": "no pending execution"}
    isolation = str(execution.get("isolation_effective") or "")
    if isolation != "worktree":
        return {
            "id": "git_worktree",
            "ok": True,
            "detail": f"isolation={isolation or 'apply'}",
        }
    wt = execution.get("worktree_path")
    branch = execution.get("exec_branch")
    sha = execution.get("exec_commit_sha")
    if not wt:
        return {"id": "git_worktree", "ok": False, "detail": "worktree path missing"}
    path = Path(str(wt))
    ok = path.is_dir()
    detail = f"{branch or 'branch?'} @ {str(sha or '')[:8] or 'no-sha'}"
    if not ok:
        detail = f"worktree missing: {wt}"
    return {"id": "git_worktree", "ok": ok, "detail": detail}


def _action_verify_check(execution: dict[str, Any] | None) -> dict[str, Any]:
    if execution is None:
        return {"id": "action_verify", "ok": True, "detail": "n/a"}
    verify_line = str(execution.get("action_verify") or "").strip()
    if not verify_line or verify_line in {"검증 기준 없음", "-", "—", "N/A", "n/a", "none"}:
        return {"id": "action_verify", "ok": False, "detail": "missing verify criterion"}
    pre = execution.get("pre_verify")
    if isinstance(pre, dict) and pre.get("blocked"):
        return {
            "id": "action_verify",
            "ok": False,
            "detail": str(pre.get("feedback") or "pre_verify blocked"),
        }
    verify_after = execution.get("verify_after_merge")
    if isinstance(verify_after, dict):
        status = str(verify_after.get("status") or "").lower()
        if status == "failed":
            return {
                "id": "action_verify",
                "ok": False,
                "detail": "post-merge verify failed",
            }
    return {"id": "action_verify", "ok": True, "detail": verify_line[:120]}


def _oracle_check(execution: dict[str, Any] | None) -> dict[str, Any]:
    if execution is None:
        return {"id": "oracle_verdict", "ok": True, "detail": "pending merge"}
    status = str(execution.get("status") or "")
    if status in OPEN_PENDING_STATUSES:
        return {"id": "oracle_verdict", "ok": True, "detail": "awaiting merge"}
    oracle = None
    verify_after = execution.get("verify_after_merge")
    if isinstance(verify_after, dict):
        oracle = verify_after.get("oracle")
    if not isinstance(oracle, dict):
        oracle = execution.get("oracle")
    if not isinstance(oracle, dict):
        return {"id": "oracle_verdict", "ok": True, "detail": "not verified yet"}
    verdict = str(oracle.get("verdict") or "").lower()
    if verdict == "fail":
        return {
            "id": "oracle_verdict",
            "ok": False,
            "detail": str(oracle.get("detail") or oracle.get("reason") or "FAIL"),
        }
    if verdict == "pass":
        return {"id": "oracle_verdict", "ok": True, "detail": "PASS"}
    return {"id": "oracle_verdict", "ok": True, "detail": verdict or "pending"}


def _open_blocks_check(run: dict[str, Any]) -> dict[str, Any]:
    from agent_lab.room.objections import open_objections

    blocks = [o for o in open_objections(run) if o.get("act") == "BLOCK"]
    count = len(blocks)
    if count:
        body = str(blocks[0].get("body") or blocks[0].get("id") or "")[:160]
        return {
            "id": "open_blocks",
            "ok": False,
            "detail": body or "open BLOCK",
            "count": count,
        }
    return {"id": "open_blocks", "ok": True, "detail": "none", "count": 0}


def _room_tasks_check(run: dict[str, Any], execution: dict[str, Any] | None) -> dict[str, Any]:
    tasks = run.get("tasks") or run.get("room_tasks")
    if not isinstance(tasks, list):
        tasks = []
    open_statuses = {"pending", "in_progress", "blocked"}
    open_tasks = [t for t in tasks if isinstance(t, dict) and str(t.get("status") or "") in open_statuses]
    if execution and execution.get("action_index") is not None:
        idx = int(execution.get("action_index"))
        linked = [t for t in open_tasks if int(t.get("plan_action_index") or -1) == idx]
        if linked:
            titles = ", ".join(str(t.get("title") or t.get("id")) for t in linked[:3])
            return {
                "id": "room_tasks",
                "ok": False,
                "detail": f"open tasks: {titles}",
                "open_count": len(linked),
            }
    return {
        "id": "room_tasks",
        "ok": True,
        "detail": f"{len(open_tasks)} open total",
        "open_count": len(open_tasks),
    }


def _diff_safety_check(execution: dict[str, Any] | None) -> dict[str, Any]:
    if execution is None:
        return {"id": "diff_safety", "ok": True, "detail": "no pending execution"}
    scan = execution.get("safety_scan")
    if not isinstance(scan, dict):
        return {"id": "diff_safety", "ok": True, "detail": "not scanned"}
    from agent_lab.diff_safety import scan_summary

    findings = scan.get("findings") or []
    blocking = [f for f in findings if isinstance(f, dict) and f.get("severity") == "block"]
    return {
        "id": "diff_safety",
        "ok": not blocking,
        "detail": scan_summary(scan) if findings else "clean",
        "findings": findings,
    }


def _pending_execution(run: dict[str, Any]) -> dict[str, Any] | None:
    return find_open_merge_pending_execution(run)


def build_merge_checks(
    run: dict[str, Any],
    *,
    pending_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pending = pending_execution if pending_execution is not None else _pending_execution(run)
    checks = [
        _worktree_check(pending),
        _worktree_hooks_check(pending),
        _action_verify_check(pending),
        _oracle_check(pending),
        _open_blocks_check(run),
        _room_tasks_check(run, pending),
        _diff_safety_check(pending),
    ]
    from agent_lab.syntax_gate import syntax_gate_enabled

    if syntax_gate_enabled():
        from agent_lab.syntax_gate import evaluate_syntax_gate

        checks.append(evaluate_syntax_gate(pending))
    merge_disabled = False
    reason: str | None = None
    for check in checks:
        if (
            check.get("id") == "oracle_verdict"
            and pending
            and str(pending.get("status") or "") in OPEN_PENDING_STATUSES
        ):
            continue
        if not check.get("ok"):
            merge_disabled = True
            reason = f"{check['id']}: {check.get('detail')}"
            break
    from agent_lab.runtime.policy import PolicyEngine

    block = PolicyEngine.execute_block_reason(run)
    if block:
        merge_disabled = True
        reason = reason or block
    if pending and isinstance(pending.get("pre_verify"), dict) and pending["pre_verify"].get("blocked"):
        merge_disabled = True
        reason = reason or str(pending["pre_verify"].get("feedback") or "pre_verify blocked")
    if pending and pending.get("needs_artifact_review"):
        arts = pending.get("verification_artifacts")
        if isinstance(arts, dict) and not arts.get("ok"):
            merge_disabled = True
            reason = reason or "artifact review incomplete"
    return {
        "checks": checks,
        "merge_disabled": merge_disabled,
        "merge_disabled_reason": reason,
        "pending_execution_id": pending.get("id") if pending else None,
    }


def public_merge_checks_payload(
    run: dict[str, Any],
    *,
    folder: Path | None = None,
) -> dict[str, Any]:
    payload = build_merge_checks(run)
    if folder is not None:
        from agent_lab.auto_merge import evaluate_auto_merge_eligibility

        payload["auto_merge"] = evaluate_auto_merge_eligibility(folder)
    else:
        exec_id = payload.get("pending_execution_id")
        payload["auto_merge"] = {
            "eligible": False,
            "reason": "session_folder_unavailable",
            "pending_execution_id": exec_id,
        }
    return payload
