"""Live soak — Telegram webhook `/approve merge` ingress (not pytest mock)."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .live_execute_spike import (
    SPIKE_MARKER,
    SPIKE_REL_PATH,
    _git,
    _git_porcelain,
    _init_spike_repo,
    _now,
    _plan_md,
    _preflight_cursor,
    _seed_plan_snapshot,
    format_report_lines,
)
from agent_lab.plan.execute import run_dry_run
from agent_lab.run.meta import patch_run_meta, read_run_meta

SOAK_TELEGRAM_CHAT_ID = 900_001

_INGRESS_CHECK_KEYS = frozenset(
    {
        "pending_approval",
        "pending_execution_present",
        "telegram_webhook_http_ok",
        "telegram_command_ok",
        "telegram_merge_confirmed_reply",
        "route_session_match",
        "approve_status_merged",
        "merge_commit_sha_present",
        "worktree_removed_after_merge",
        "exec_branch_removed_after_merge",
    }
)

_CONTENT_CHECK_KEYS = frozenset(
    {
        "base_head_changed",
        "base_branch_contains_marker",
        "head_is_merge_commit",
    }
)


def _write_soak_gateway_config(path: Path) -> None:
    path.write_text(
        """
[telegram]
enabled = true
bot_token = "soak-ingress-token"
allowed_chat_ids = [900001]

[adapters]
enabled = ["telegram"]
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_soak_routes_config(path: Path, *, session_id: str) -> None:
    path.write_text(
        f"""
[default]
session_id = "{session_id}"
gate_profile = "assistant"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _patch_sessions_root(parent: Path) -> None:
    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    session_mod.SESSIONS_DIR = parent
    deps_mod.SESSIONS_DIR = parent


def _prepare_soak_merge_gate(folder: Path, execution_id: str) -> bool:
    """Tier D tests Telegram ingress — clear artifact gate on disposable soak sessions."""
    changed = False

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        nonlocal changed
        for row in run.get("executions") or []:
            if not isinstance(row, dict) or str(row.get("id") or "") != execution_id:
                continue
            if not row.get("needs_artifact_review"):
                continue
            changed = True
            row["needs_artifact_review"] = False
            row["verification_artifacts"] = {
                "ok": True,
                "soak_bypass": True,
                "pdf_path": "soak/disposable.pdf",
                "pdf_page_count": 1,
                "break_report": {"baselinePdfPageCount": 1, "appliedBreaks": 0},
            }
        return run

    patch_run_meta(folder, _patch)
    return changed


def _post_telegram_merge_webhook(*, chat_id: int, session_id: str) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.server.main import app

    client = TestClient(app)
    update = {
        "message": {
            "chat": {"id": chat_id},
            "text": "/approve merge",
        }
    }
    response = client.post("/api/gateway/telegram/webhook", json=update)
    body: dict[str, Any] | None = None
    try:
        loaded = response.json()
        if isinstance(loaded, dict):
            body = loaded
    except Exception:
        body = None
    return {
        "status_code": response.status_code,
        "body": body,
        "session_id": session_id,
    }


def run_live_telegram_merge_ingress_soak(
    *,
    work_parent: Path | None = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    """
    Tier D soak: real Cursor dry-run → pending merge → HTTP Telegram webhook
    `/approve merge` → disposable repo merged.

    Never targets agent-lab main. Requires AGENT_LAB_RUN_LIVE=1 and Cursor SDK.
    """
    from agent_lab.agents.cursor_agent import is_available
    from agent_lab.runtime.snapshot import pending_execution

    report: dict[str, Any] = {
        "kind": "live_telegram_merge_ingress",
        "started_at": _now(),
        "status": "skipped",
        "checks": {},
        "preflight": {},
        "execution": None,
        "telegram": None,
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
            preflight.get("reason") or preflight.get("failure_code") or "cursor preflight not ready"
        )
        report["finished_at"] = _now()
        return report

    parent = work_parent or Path(tempfile.mkdtemp(prefix="agent-lab-live-tg-merge-"))
    owns_parent = work_parent is None
    repo = parent / "repo"
    session = parent / "session"
    session_id = session.name
    config_dir = parent / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    gateway_path = config_dir / "gateway.toml"
    routes_path = config_dir / "routes.toml"

    os.environ["AGENT_LAB_SESSIONS_DIR"] = str(parent)
    os.environ["AGENT_LAB_GATEWAY_CONFIG"] = str(gateway_path)
    os.environ["AGENT_LAB_ROUTES_CONFIG"] = str(routes_path)
    _patch_sessions_root(parent)
    _write_soak_gateway_config(gateway_path)
    _write_soak_routes_config(routes_path, session_id=session_id)

    session.mkdir(parents=True, exist_ok=True)
    run_meta = {
        "workflow_id": "room",
        "run_schema_version": 1,
        "gate_profile": "assistant",
        "topic": "live telegram merge ingress soak",
        "created_at": _now(),
    }
    from agent_lab.run.meta import write_run_meta

    write_run_meta(session, run_meta)

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
        }

        worktree_path = Path(str(execution.get("worktree_path") or ""))
        git_root = Path(str(execution.get("git_root") or repo))
        checks: dict[str, bool] = {
            "main_clean_before": main_before == "",
            "isolation_worktree": execution.get("isolation_effective") == "worktree",
            "pending_approval": execution.get("status") == "pending_approval",
            "main_clean_after_dry_run": _git_porcelain(git_root) == "",
            "worktree_exists_before_ingress": worktree_path.is_dir(),
        }
        report["checks"] = checks

        if execution.get("status") != "pending_approval":
            report["status"] = "no_go"
            report["errors"].append("dry-run did not stop at pending_approval")
            return report

        pending_before = pending_execution(read_run_meta(session))
        checks["pending_execution_present"] = bool(pending_before and pending_before.get("id"))

        exec_id = str(execution.get("id") or "")
        checks["artifact_gate_bypassed"] = _prepare_soak_merge_gate(session, exec_id)

        tg = _post_telegram_merge_webhook(
            chat_id=SOAK_TELEGRAM_CHAT_ID,
            session_id=session_id,
        )
        report["telegram"] = tg
        body = tg.get("body") if isinstance(tg.get("body"), dict) else {}
        checks["telegram_webhook_http_ok"] = int(tg.get("status_code") or 0) == 200
        checks["telegram_command_ok"] = bool(body.get("ok"))
        reply = str(body.get("reply") or "")
        checks["telegram_merge_confirmed_reply"] = (
            "merge approved" in reply.lower() or "merge confirmed" in reply.lower()
        )

        run_after = read_run_meta(session)
        merged_row = next(
            (
                row
                for row in (run_after.get("executions") or [])
                if isinstance(row, dict) and row.get("id") == execution.get("id")
            ),
            {},
        )
        merge = dict(merged_row.get("merge") or {})
        report["merge"] = {
            "status": merge.get("status"),
            "commit_sha": merge.get("commit_sha"),
            "execution_status": merged_row.get("status"),
            "reply": reply,
        }

        merge_commit_sha = str(merge.get("commit_sha") or "")
        branch = str(execution.get("exec_branch") or "")
        branch_list = _git(git_root, "branch", "--list", branch) if branch else ""
        base_text = (repo / SPIKE_REL_PATH).read_text(encoding="utf-8")
        head_sha = _git(git_root, "rev-parse", "HEAD")

        checks.update(
            {
                "approve_status_merged": merged_row.get("status") == "merged",
                "merge_commit_sha_present": bool(merge_commit_sha),
                "head_is_merge_commit": bool(merge_commit_sha) and head_sha == merge_commit_sha,
                "base_head_changed": head_sha != pre_merge_sha,
                "base_branch_contains_marker": SPIKE_MARKER in base_text,
                "main_clean_after_merge": _git_porcelain(git_root) == "",
                "worktree_removed_after_merge": not worktree_path.exists(),
                "exec_branch_removed_after_merge": branch_list.strip() == "",
                "route_session_match": (body.get("route") or {}).get("session_id") == session_id,
            }
        )
        report["checks"] = checks
        report["rollback"] = {
            "repo": str(repo.resolve()),
            "pre_merge_sha": pre_merge_sha,
            "reset_command": f"git -C {repo.resolve()} reset --hard {pre_merge_sha}",
        }

        failed = [k for k, v in checks.items() if not v]
        ingress_failed = [k for k in failed if k in _INGRESS_CHECK_KEYS]
        content_failed = [k for k in failed if k in _CONTENT_CHECK_KEYS]
        report["ingress_status"] = "go" if not ingress_failed else "no_go"
        report["content_status"] = "go" if not content_failed else "no_go"
        if content_failed:
            report["warnings"] = [
                "Cursor dry-run did not land LIVE_M0_OK — ingress still valid for Tier D",
            ]
        # Tier D GO = Telegram webhook merge ingress (content is Tier C overlap).
        report["status"] = report["ingress_status"]
        if ingress_failed:
            report["errors"].append(f"ingress failed: {', '.join(ingress_failed)}")
        if content_failed:
            report["errors"].append(f"content checks failed: {', '.join(content_failed)}")
    except Exception as exc:  # noqa: BLE001 — operator report surface
        report["status"] = "no_go"
        report["errors"].append(str(exc))
    finally:
        report["finished_at"] = _now()
        if cleanup and owns_parent and parent.exists():
            shutil.rmtree(parent, ignore_errors=True)

    return report


def format_telegram_soak_lines(report: dict[str, Any]) -> list[str]:
    lines = format_report_lines(report)
    tg = report.get("telegram") or {}
    if tg:
        lines.append(f"  telegram_http: {tg.get('status_code')}")
        body = tg.get("body") if isinstance(tg.get("body"), dict) else {}
        if body.get("reply"):
            lines.append(f"  telegram_reply: {body.get('reply')}")
    return lines
