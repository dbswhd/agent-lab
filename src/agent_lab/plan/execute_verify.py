"""Merge-checkpoint arming and post-merge verify/repair helpers for thin execute."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

from agent_lab.run.state import RunState

from agent_lab.run.meta import patch_run_meta
from agent_lab.plan.execute_worktree import (
    ExecWorktree,
)
from agent_lab.runtime.adapters import (
    invoke_repair,
    verify_follow_ups,
)


def _arm_merge_checkpoint(
    folder: Path,
    *,
    execution_id: str,
    target: dict[str, Any],
    op: str,
    worktree: ExecWorktree | None = None,
    exec_commit_sha: str | None = None,
) -> None:
    """Persist a write-ahead checkpoint to run.json *before* an irreversible merge (G3).

    The merge (``git merge --no-ff`` on the base branch) is irreversible, but the
    ``status="merged"`` persist only happens *after* it. A crash in between leaves
    base advanced while run.json still reads ``pending_approval`` with no breadcrumb.
    This durably records — on its own ``patch_run_meta`` flush, not the end-of-function
    one — enough git anchors (base HEAD before, exec tip, branch, worktree) for the
    boot-time ``crash_recovery`` scan to reconcile run.json against git ground-truth.
    """
    from agent_lab.plan.execute import _now, _exec_worktree_from_execution

    ew = worktree if worktree is not None else _exec_worktree_from_execution(target)
    base_sha_before = ew.base_sha
    try:
        head = subprocess.run(
            ["git", "-C", str(ew.git_root), "rev-parse", ew.base_branch],
            capture_output=True,
            text=True,
            check=False,
        )
        if head.returncode == 0 and head.stdout.strip():
            base_sha_before = head.stdout.strip()
    except Exception:
        pass
    checkpoint = {
        "phase": "merging",
        "op": op,
        "started_at": _now(),
        "git_root": str(ew.git_root),
        "worktree_path": str(ew.worktree_path),
        "base_branch": ew.base_branch,
        "base_sha_before": base_sha_before,
        "exec_branch": ew.branch,
        "exec_commit_sha": str(exec_commit_sha or target.get("exec_commit_sha") or ""),
        "prev_status": target.get("status"),
        "prev_merge": dict(target.get("merge") or {}),
        "snapshot_id": str(target.get("snapshot_id") or target.get("id") or ""),
    }
    target["checkpoint"] = checkpoint

    def _patch(run: RunState) -> RunState:
        for row in run.get("executions") or []:
            if isinstance(row, dict) and row.get("id") == execution_id:
                row["checkpoint"] = checkpoint
        return run

    patch_run_meta(folder, _patch)


def _clear_merge_checkpoint(target: dict[str, Any]) -> None:
    """Drop the in-memory checkpoint; the end-of-function persist removes it from disk."""
    target.pop("checkpoint", None)


def _execution_verify_action(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "what": target.get("action_what"),
        "where": target.get("action_where"),
        "verify": target.get("action_verify"),
    }


def _merged_verify_paths(target: dict[str, Any]) -> list[str | Path]:
    paths: list[str] = []
    for key in (
        "source_touched_paths",
        "touched_paths",
        "expected_paths",
        "verification_paths",
        "monitored_paths",
    ):
        for raw in target.get(key) or []:
            path = str(raw)
            if path and path not in paths:
                paths.append(path)
    return cast(list[str | Path], paths)


def _verify_workspace_root(target: dict[str, Any]) -> Path | None:
    raw = target.get("git_root") or target.get("workspace_root")
    return Path(str(raw)) if raw else None


def _notify_merge_conflict_mission(
    folder: Path,
    target: dict[str, Any],
) -> None:
    from agent_lab.runtime.events import RuntimeEvent
    from agent_lab.runtime.runtime import dispatch

    merge_raw = target.get("merge")
    merge: dict[str, Any] = merge_raw if isinstance(merge_raw, dict) else {}
    files = [str(f) for f in (merge.get("conflict_files") or []) if f]
    detail = ", ".join(files) if files else "unknown files"
    idx = target.get("action_index")
    dispatch(
        folder,
        RuntimeEvent.EXECUTE_STRUCTURAL_FAIL,
        {
            "reason": f"merge conflict: {detail}",
            "action_index": int(idx) if idx is not None else None,
        },
    )


def _record_verify_after_merge(
    folder: Path,
    target: dict[str, Any],
    *,
    verify_retries: int | None = None,
) -> dict[str, Any]:
    from agent_lab.plan.execute import _now, verify_after_merge

    retries = int(verify_retries if verify_retries is not None else target.get("verify_retries") or 0)
    checked_at = _now()
    evidence = verify_after_merge(
        _execution_verify_action(target),
        _merged_verify_paths(target),
        session_folder=folder,
        workspace_root=_verify_workspace_root(target),
        verify_retries=retries,
    )
    evidence["checked_at"] = checked_at
    oracle = dict(evidence.get("oracle") or {})
    oracle["checked_at"] = checked_at
    evidence["oracle"] = oracle
    src = str(oracle.get("source") or "mock")
    evidence["source"] = "live_oracle" if src == "live" else "mock_oracle"
    target["verify_after_merge"] = evidence
    target["oracle"] = oracle
    target["verify_retries"] = retries
    target["reverify_endpoint"] = "/api/sessions/{session_id}/execute/reverify"
    history = list(target.get("verify_history") or [])
    history.append(
        {
            "attempt": retries,
            "checked_at": checked_at,
            "status": evidence.get("status"),
            "oracle": oracle,
        }
    )
    target["verify_history"] = history
    if str(target.get("status") or "") == "merged":
        from agent_lab.plan.execute_merge import archive_executed_diff

        exec_id = str(target.get("id") or "")
        if exec_id:
            archive_executed_diff(folder, execution_id=exec_id, execution=target)
    from agent_lab.core.mission_loop import get_mission_loop
    from agent_lab.run.meta import read_run_meta
    from agent_lab.runtime.runtime import dispatch_prepare_verify, dispatch_verify_result

    exec_id = str(target.get("id") or "")
    if exec_id:
        phase = str(get_mission_loop(read_run_meta(folder)).get("phase") or "")
        if phase in {"MERGE_REVIEW", "REPAIR"}:
            dispatch_prepare_verify(folder, execution_id=exec_id)

    idx = int(target.get("action_index") or 0)
    verdict = str((oracle.get("verdict") or evidence.get("status") or "")).lower()
    reason = str(oracle.get("detail") or oracle.get("feedback") or oracle.get("reason") or "")
    from agent_lab.trace_recorder import record_control_span

    record_control_span(
        folder,
        name="oracle_verify",
        status=verdict or "unknown",
        data={
            "execution_id": str(target.get("id") or ""),
            "source": evidence.get("source"),
            "retries": retries,
        },
    )
    dispatch_verify_result(
        folder,
        action_index=idx,
        verdict=verdict,
        reason=reason,
        oracle=oracle,
    )
    exec_id = str(target.get("id") or "")
    if exec_id:
        from agent_lab.evidence_sync import on_verify_recorded

        on_verify_recorded(folder, exec_id, evidence=evidence)
    try:
        from agent_lab.skill_drafts import (
            maybe_create_skill_draft_from_verify,
            verify_evidence_passed,
        )

        if verify_evidence_passed(evidence):
            maybe_create_skill_draft_from_verify(folder, target, evidence)
    except Exception:
        pass

    from agent_lab.outcome_harvester import record_execute_outcome

    record_execute_outcome(folder, target)
    try:
        from agent_lab.autonomy_promotion import record_l0_to_l1_sample

        record_l0_to_l1_sample(folder, target)
    except Exception:
        pass
    return evidence


def _repair_prompt(target: dict[str, Any], *, attempt: int) -> str:
    from agent_lab.plan.execute import MAX_VERIFY_RETRIES

    oracle_raw = target.get("oracle")
    oracle: dict[str, Any] = oracle_raw if isinstance(oracle_raw, dict) else {}
    reason = str(oracle.get("detail") or "Oracle verification failed")
    paths = ", ".join(str(p) for p in _merged_verify_paths(target)) or "(plan paths unavailable)"
    return f"""Layer 3 repair attempt {attempt}/{MAX_VERIFY_RETRIES}.

The previous merge completed, but the independent Oracle returned FAIL:
{reason}

Repair only the current plan action in this isolated worktree.
- 무엇을: {target.get("action_what") or target.get("action_key") or "plan action"}
- 어디서: {target.get("action_where") or paths}
- 검증: {target.get("action_verify") or "verify field missing"}
- 관련 경로: {paths}

Re-read the files, make the smallest required fix, and run the named verification.
End with `VERIFICATION: PASS — ...` or `VERIFICATION: FAIL — ...`."""


def _call_repair_agent(
    agent_id: str,
    *,
    target: dict[str, Any],
    worktree_path: Path,
    permissions: dict[str, Any] | None,
    attempt: int,
    session_folder: Path | None = None,
) -> str:
    prompt = _repair_prompt(target, attempt=attempt)
    if session_folder is not None:
        from agent_lab.runtime.context import enrich_execute_prompt
        from agent_lab.run.meta import read_run_meta
        from agent_lab.session.plugin_runtime import (
            enrich_execute_permissions,
            execute_plugin_prompt_addon,
        )

        permissions = enrich_execute_permissions(permissions, session_folder)
        prompt = execute_plugin_prompt_addon(prompt, session_folder, agent_id)
        prompt = enrich_execute_prompt(
            prompt, read_run_meta(session_folder), session_folder=session_folder
        )
    from agent_lab.runtime.adapters import RepairInvokeRequest

    effective = dict(permissions or {})
    effective["_discuss_cwd"] = str(worktree_path.resolve())
    return invoke_repair(
        agent_id,  # type: ignore[arg-type]
        RepairInvokeRequest(
            system="You repair a merged plan action after independent verification failed.",
            user=prompt,
            permissions=effective,
            cwd=worktree_path,
            verify_follow_ups=verify_follow_ups(str(target.get("action_verify") or "")),
        ),
    )


def _append_repair_history(
    target: dict[str, Any],
    repair: dict[str, Any],
) -> None:
    history = list(target.get("repair_history") or [])
    history.append(repair)
    target["repair_history"] = history
    target["last_repair"] = repair
