"""PolicyEngine — gate snapshot + hook checks (H4 unified policy layer)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_lab.room_hooks import PreExecuteBlocked


@dataclass(slots=True)
class PolicyResult:
    """Outcome of a policy check (gates, hooks, objections)."""

    allowed: bool
    reason: str | None = None
    source: str | None = None
    gate_snapshot: dict[str, Any] | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return not self.allowed


class PolicyEngine:
    """Single entry for orchestration policy before discuss/execute transitions."""

    @staticmethod
    def gate_snapshot(run_meta: dict[str, Any] | None) -> dict[str, Any]:
        from agent_lab.gate_snapshot import compute_gate_snapshot

        return compute_gate_snapshot(run_meta)

    @staticmethod
    def format_gate_block(snapshot: dict[str, Any]) -> str:
        from agent_lab.gate_snapshot import format_gate_snapshot_block

        return format_gate_snapshot_block(snapshot)

    @staticmethod
    def execute_block_reason(run_meta: dict[str, Any] | None) -> str | None:
        snap = PolicyEngine.gate_snapshot(run_meta)
        if snap.get("block_source"):
            return str(snap.get("block_reason") or snap.get("block_source") or "")
        return None

    @staticmethod
    def check_execute_allowed(
        run_meta: dict[str, Any] | None,
        action_index: int,
        action_kind: Any = None,
    ) -> PolicyResult:
        from agent_lab.room_objections import execute_block_reason_for_action

        snap = PolicyEngine.gate_snapshot(run_meta)
        if run_meta and run_meta.get("schedule_sandbox"):
            return PolicyResult(
                allowed=False,
                reason="schedule_sandbox_read_only",
                source="schedule_sandbox",
                gate_snapshot=snap,
            )
        reason = execute_block_reason_for_action(run_meta, action_index, action_kind)
        if reason:
            return PolicyResult(
                allowed=False,
                reason=reason,
                source="open_objection",
                gate_snapshot=snap,
            )
        if not (snap.get("gates") or {}).get("execute", {}).get("open", True):
            return PolicyResult(
                allowed=False,
                reason=str(snap.get("block_reason") or "execute blocked"),
                source=str(snap.get("block_source") or "gate"),
                gate_snapshot=snap,
            )
        return PolicyResult(allowed=True, gate_snapshot=snap)

    @staticmethod
    def assert_execute_allowed(
        run_meta: dict[str, Any] | None,
        action_index: int,
        action_kind: Any = None,
    ) -> PolicyResult:
        gate = PolicyEngine.check_execute_allowed(run_meta, action_index, action_kind)
        if not gate.allowed:
            if gate.source == "schedule_sandbox":
                raise RuntimeError(gate.reason or "schedule_sandbox_read_only")
            from agent_lab.room_objections import ObjectionBlocksExecute

            raise ObjectionBlocksExecute(
                gate.reason or "execute blocked",
                objections=[],
            )
        from agent_lab.room_objections import assert_execute_allowed as _assert

        _assert(run_meta, action_index, action_kind)
        return PolicyResult(allowed=True, gate_snapshot=gate.gate_snapshot)

    @staticmethod
    def check_pre_execute(
        run_meta: dict[str, Any],
        action: dict[str, Any],
        *,
        session_folder: Path | None = None,
        session_id: str = "",
    ) -> PolicyResult:
        from agent_lab.room_hooks import run_pre_execute_hooks

        pre = run_pre_execute_hooks(
            run_meta,
            action,
            session_folder=session_folder,
            session_id=session_id,
        )
        snap = PolicyEngine.gate_snapshot(run_meta)
        if pre.get("blocked"):
            return PolicyResult(
                allowed=False,
                reason=str(pre.get("feedback") or "pre_execute hook blocked"),
                source="pre_execute",
                gate_snapshot=snap,
                details=pre,
            )
        return PolicyResult(allowed=True, gate_snapshot=snap, details=pre)

    @staticmethod
    def require_pre_execute(
        run_meta: dict[str, Any],
        action: dict[str, Any],
        *,
        session_folder: Path | None = None,
        session_id: str = "",
    ) -> PolicyResult:
        result = PolicyEngine.check_pre_execute(
            run_meta,
            action,
            session_folder=session_folder,
            session_id=session_id,
        )
        if result.blocked:
            raise PreExecuteBlocked(
                str(result.reason or "pre_execute hook blocked"),
                pre_verify=result.details,
            )
        return result

    @staticmethod
    def check_task_completed(
        run_meta: dict[str, Any],
        task: dict[str, Any],
        *,
        session_folder: Path | None = None,
        session_id: str = "",
    ) -> PolicyResult:
        from agent_lab.room_hooks import run_task_completed_hooks

        block_msg = run_task_completed_hooks(
            run_meta,
            task,
            session_folder=session_folder,
            session_id=session_id,
        )
        if block_msg:
            return PolicyResult(
                allowed=False,
                reason=block_msg,
                source="task_completed",
                gate_snapshot=PolicyEngine.gate_snapshot(run_meta),
            )
        return PolicyResult(allowed=True, gate_snapshot=PolicyEngine.gate_snapshot(run_meta))
