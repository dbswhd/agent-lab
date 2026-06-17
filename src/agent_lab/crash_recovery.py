"""Durable crash-recovery for in-flight worktree merges (G3).

The execute lifecycle has an irreversible window: ``merge_exec_branch`` runs
``git merge --no-ff`` on the base branch, but ``status="merged"`` is only
persisted *after*. A crash in between leaves the base branch advanced while
``run.json`` still reads ``pending_approval`` with no breadcrumb.

``plan_execute._arm_merge_checkpoint`` durably records a ``checkpoint`` on the
execution row *before* the merge. On server boot, :func:`reconcile_crashed_merges`
scans every session for live ``checkpoint.phase == "merging"`` rows and, using
**git ground-truth** (did the exec commit actually land on base?), reconciles
``run.json`` to match reality:

- merge landed   → finalize to ``merged`` (bookkeeping only; verify NOT auto-run)
- merge missed   → roll back to the pre-attempt status (no git action)
- ambiguous/undeterminable → quarantine for a human, do nothing destructive

It never performs a *new* irreversible git operation (honors P5:
irreversible → human gate), is idempotent (safe every boot), and never raises.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TRUE = frozenset({"1", "true", "yes", "on"})
_MAX_RECOVERY_LOG = 50


def crash_recovery_enabled() -> bool:
    """Opt-out via ``AGENT_LAB_CRASH_RECOVERY=0`` (default on)."""
    import os

    raw = os.getenv("AGENT_LAB_CRASH_RECOVERY")
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() in _TRUE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _decide(cp: dict[str, Any]) -> tuple[str, str | None]:
    """Return (action, info) where action ∈ {merged, rollback, quarantine}.

    ``info`` is the base HEAD sha for ``merged``, or a reason string for
    ``quarantine``. Pure git reads — no mutation.
    """
    git_root = str(cp.get("git_root") or "")
    base_branch = str(cp.get("base_branch") or "")
    exec_sha = str(cp.get("exec_commit_sha") or "")
    base_before = str(cp.get("base_sha_before") or "")
    if not git_root or not base_branch or not Path(git_root).exists():
        return "quarantine", "undeterminable"
    head = _git(Path(git_root), "rev-parse", base_branch)
    if head.returncode != 0 or not head.stdout.strip():
        return "quarantine", "undeterminable"
    base_head = head.stdout.strip()
    if not exec_sha:
        return "quarantine", "undeterminable"
    landed = _git(Path(git_root), "merge-base", "--is-ancestor", exec_sha, base_branch).returncode == 0

    if landed and base_head != base_before:
        return "merged", base_head
    if not landed and base_head == base_before:
        return "rollback", None
    if landed and base_head == base_before:
        return "quarantine", "ambiguous_noop"
    # not landed and base moved by something else
    return "quarantine", "base_moved_elsewhere"


def _recovery_prompt(action: str, *, row: dict[str, Any], info: str | None) -> str:
    label = str(row.get("action_label") or row.get("action_id") or row.get("id") or "execution")
    if action == "merged":
        return (
            f"Crash-recovered merge for '{label}': the merge committed to the base "
            f"branch before the crash, so run.json was reconciled to merged. "
            f"verify-after-merge was NOT run — trigger it when ready."
        )
    if action == "rollback":
        prev = str(row.get("status") or "pending_approval")
        return (
            f"Merge for '{label}' crashed before committing; the base branch is "
            f"untouched, so it was rolled back to {prev}. Re-approve to retry."
        )
    return (
        f"Merge for '{label}' crashed mid-flight and could not be auto-reconciled "
        f"({info}). It is quarantined for manual review."
    )


def _append_recovery_log(run: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    log = list(run.get("crash_recovery_log") or [])
    log.append(entry)
    run["crash_recovery_log"] = log[-_MAX_RECOVERY_LOG:]
    return run


def _add_inbox_notice(run: dict[str, Any], *, exec_id: str, action: str, prompt: str) -> dict[str, Any]:
    """Append a deduped human-inbox build notice (no dispatch, boot-safe)."""
    from agent_lab.human_inbox import append_inbox_item, inbox_items, new_inbox_item

    source = f"crash_recovery:{exec_id}"
    for item in inbox_items(run):
        if item.get("source") == source and item.get("status") == "pending":
            return run
    item = new_inbox_item(
        kind="build",
        source=source,
        prompt=prompt,
        summary=f"crash-recovery: {action}",
        trigger="crash_recovery",
        harvest_key=source,
    )
    return append_inbox_item(run, item)


def _apply_decision(
    folder: Path,
    *,
    exec_id: str,
    cp: dict[str, Any],
    action: str,
    info: str | None,
) -> None:
    from agent_lab.run_meta import patch_run_meta

    ts = _now()

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        for row in run.get("executions") or []:
            if not isinstance(row, dict) or row.get("id") != exec_id:
                continue
            if action == "merged":
                merge = dict(row.get("merge") or {})
                merge["status"] = "merged"
                merge["commit_sha"] = info
                merge["completed_at"] = ts
                merge["recovered"] = True
                row["merge"] = merge
                row["status"] = "merged"
                row["completed_at"] = ts
                row["recovery"] = {"action": "reconciled_merged", "at": ts, "op": cp.get("op"), "commit_sha": info}
                row.pop("checkpoint", None)
            elif action == "rollback":
                row["status"] = cp.get("prev_status") or "pending_approval"
                row["merge"] = dict(cp.get("prev_merge") or {})
                row["recovery"] = {"action": "rolled_back", "at": ts, "op": cp.get("op")}
                row.pop("checkpoint", None)
            else:  # quarantine
                quarantined = dict(cp)
                quarantined["phase"] = "quarantined"  # stop re-matching on next boot
                quarantined["recovery"] = info
                row["checkpoint"] = quarantined
                row["recovery"] = {"action": "quarantined", "at": ts, "op": cp.get("op"), "reason": info}
            prompt = _recovery_prompt(action, row=row, info=info)
            run = _append_recovery_log(
                run,
                {"exec_id": exec_id, "action": action, "info": info, "op": cp.get("op"), "at": ts},
            )
            run = _add_inbox_notice(run, exec_id=exec_id, action=action, prompt=prompt)
            break
        return run

    patch_run_meta(folder, _patch)

    # Filesystem cleanup AFTER the atomic run.json write (idempotent, best-effort).
    if action == "merged":
        try:
            from agent_lab.plan_execute_worktree import remove_exec_worktree

            remove_exec_worktree(
                folder,
                exec_id=exec_id,
                git_root=Path(str(cp.get("git_root"))),
                branch=str(cp.get("exec_branch") or ""),
                worktree_path=Path(str(cp.get("worktree_path"))) if cp.get("worktree_path") else None,
            )
        except Exception:
            pass
        snap = str(cp.get("snapshot_id") or "")
        if snap:
            try:
                from agent_lab.plan_execute_snapshot import delete_snapshot

                delete_snapshot(folder, snap)
            except Exception:
                pass


def _crashed_rows(run: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any], bool]]:
    """Return (row, checkpoint, is_pre_feature) for executions needing recovery."""
    out: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
    for row in run.get("executions") or []:
        if not isinstance(row, dict):
            continue
        cp = row.get("checkpoint") if isinstance(row.get("checkpoint"), dict) else None
        if cp is not None and cp.get("phase") == "merging":
            out.append((row, cp, False))
            continue
        # Pre-feature crash: a pre-G3 merge attempt with no checkpoint. We lack the
        # git anchors to trust git ground-truth, so quarantine unconditionally.
        recovery = row.get("recovery") if isinstance(row.get("recovery"), dict) else None
        merge = row.get("merge") if isinstance(row.get("merge"), dict) else {}
        if cp is None and recovery is None and row.get("status") == "pending_approval" and merge.get("attempted_at"):
            out.append((row, {}, True))
    return out


def _reconcile_session(folder: Path) -> dict[str, int]:
    from agent_lab.run_meta import read_run_meta

    counts = {"reconciled_merged": 0, "rolled_back": 0, "quarantined": 0}
    run = read_run_meta(folder)
    for row, cp, pre_feature in _crashed_rows(run):
        exec_id = str(row.get("id") or "")
        if not exec_id:
            continue
        if pre_feature:
            action, info = "quarantine", "pre_feature_no_checkpoint"
        else:
            action, info = _decide(cp)
        _apply_decision(folder, exec_id=exec_id, cp=cp, action=action, info=info)
        if action == "merged":
            counts["reconciled_merged"] += 1
        elif action == "rollback":
            counts["rolled_back"] += 1
        else:
            counts["quarantined"] += 1
    return counts


def reconcile_crashed_merges(*, sessions_root: Path | None = None) -> dict[str, Any]:
    """Idempotent boot scan. Reconcile crashed in-flight merges; never raises.

    Returns a summary ``{scanned, reconciled_merged, rolled_back, quarantined,
    errors, sessions}`` where ``scanned`` counts sessions inspected.
    """
    summary: dict[str, Any] = {
        "scanned": 0,
        "reconciled_merged": 0,
        "rolled_back": 0,
        "quarantined": 0,
        "errors": 0,
        "sessions": [],
    }
    if sessions_root is None:
        from agent_lab.session import SESSIONS_DIR

        sessions_root = SESSIONS_DIR
    if not sessions_root.is_dir():
        return summary
    for folder in sorted(sessions_root.iterdir()):
        if not folder.is_dir() or folder.name.startswith((".", "_")):
            continue
        if not (folder / "run.json").is_file():
            continue
        summary["scanned"] += 1
        try:
            counts = _reconcile_session(folder)
        except Exception as exc:  # one bad session must not abort the scan
            summary["errors"] += 1
            summary["sessions"].append({"session": folder.name, "error": str(exc)[:200]})
            continue
        if any(counts.values()):
            summary["reconciled_merged"] += counts["reconciled_merged"]
            summary["rolled_back"] += counts["rolled_back"]
            summary["quarantined"] += counts["quarantined"]
            summary["sessions"].append({"session": folder.name, **counts})
    return summary
