"""Wire evidence ledger + gates to execute lifecycle (MB-3, MB-4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.evidence_gates import patch_execution_gates
from agent_lab.evidence_ledger import append_evidence


def on_dry_run_recorded(
    folder: Path,
    execution: dict[str, Any],
    *,
    action_index: int | None = None,
) -> None:
    exec_id = str(execution.get("id") or "")
    append_evidence(
        folder,
        {
            "phase": "DRY_RUN",
            "kind": "dry_run",
            "execution_id": exec_id,
            "action_index": action_index or execution.get("action_index"),
            "status": execution.get("status"),
            "detail": execution.get("diff_stat"),
            "refs": [f"run.json#executions/{exec_id}"] if exec_id else [],
        },
    )
    if exec_id:
        patch_execution_gates(folder, exec_id)


def on_merge_approved(
    folder: Path,
    execution_id: str,
    *,
    commit_sha: str | None = None,
) -> None:
    append_evidence(
        folder,
        {
            "phase": "MERGE",
            "kind": "merge_approve",
            "execution_id": execution_id,
            "detail": commit_sha,
            "refs": [f"run.json#executions/{execution_id}"],
        },
    )
    patch_execution_gates(folder, execution_id)


def on_verify_recorded(
    folder: Path,
    execution_id: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> None:
    oracle = {}
    if isinstance(evidence, dict):
        oracle = evidence.get("oracle") if isinstance(evidence.get("oracle"), dict) else {}
    append_evidence(
        folder,
        {
            "phase": "VERIFY",
            "kind": "oracle",
            "execution_id": execution_id,
            "exit": 0 if str(oracle.get("verdict") or "").lower() == "pass" else 1,
            "detail": str(oracle.get("detail") or oracle.get("verdict") or ""),
            "refs": [f"run.json#executions/{execution_id}"],
        },
    )
    patch_execution_gates(folder, execution_id)


def on_repair_recorded(
    folder: Path,
    execution_id: str,
    *,
    attempt: int,
    detail: str | None = None,
) -> None:
    append_evidence(
        folder,
        {
            "phase": "REPAIR",
            "kind": "repair",
            "execution_id": execution_id,
            "detail": detail or f"attempt {attempt}",
            "refs": [f"run.json#executions/{execution_id}"],
        },
    )
    patch_execution_gates(folder, execution_id)
