from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from agent_lab.mission.decision_queue import AnswerDecision, DecisionTransitionError, new_decision
from agent_lab.mission.decision_repository import DecisionRepository, decision_journal_path
from agent_lab.mission.kernel import (
    ApprovePlan,
    Mission,
    MissionState,
    OpenPlan,
    RejectPlan,
)
from agent_lab.mission.messages import JsonValue
from agent_lab.mission.projection import (
    MissionLoopStatusProjection,
    apply_mission_loop_status_projection,
    project_mission_loop_status as _project_status,
)
from agent_lab.mission.repository import MissionRepository
from agent_lab.plan.pending import plan_content_hash
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.run.state import RunState, RunStateLike
from agent_lab.plan.workflow_state import apply_plan_substate_patch


def project_mission_loop_status(
    mission: Mission,
    run: RunStateLike,
) -> MissionLoopStatusProjection:
    return _project_status(mission, run)


def _project_mission_loop_status(folder: Path, mission: Mission) -> None:
    apply_mission_loop_status_projection(folder, mission)


class MissionApplicationError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class MissionApplication:
    session_folder: Path
    goal: str

    @property
    def repository(self) -> MissionRepository:
        return MissionRepository(
            self.session_folder / ".agent-lab" / "mission-events.jsonl",
            self.session_folder.name,
            self.goal,
        )

    def load(self) -> Mission:
        return self.repository.load()

    def _mission_authority_enabled(self) -> bool:
        from agent_lab.mission.inbox_application import mission_authority_enabled

        return mission_authority_enabled(self.session_folder)

    def open_inbox_item(self, item: Mapping[str, JsonValue]) -> Mission:
        from agent_lab.mission.inbox_application import open_inbox_item

        return open_inbox_item(self, item)

    def resolve_inbox_item(
        self,
        item_id: str,
        *,
        status: str = "resolved",
        selected: list[str] | None = None,
        decision: str | None = None,
        note: str | None = None,
        expected_version: int | None = None,
    ) -> Mission:
        from agent_lab.mission.inbox_application import resolve_inbox_item

        try:
            return resolve_inbox_item(
                self,
                item_id,
                status=status,
                selected=selected,
                decision=decision,
                note=note,
                expected_version=expected_version,
            )
        except ValueError as exc:
            raise MissionApplicationError(str(exc)) from exc

    def approve_plan(self) -> Mission:
        plan = self._read_plan()
        current = self.load()
        plan_hash = plan_content_hash(plan)
        if current.state is MissionState.READY_TO_EXECUTE and current.approved_plan_hash == plan_hash:
            _project_mission_loop_status(self.session_folder, current)
            self._project_plan(current)
            return current
        if not (current.state is MissionState.AWAITING_PLAN_DECISION and current.current_plan_hash == plan_hash):
            open_key = f"plan-open:{plan_hash}:{current.plan_revision + 1}"
            current = self.repository.dispatch(OpenPlan(plan_hash), idempotency_key=open_key)
        mission = self.repository.dispatch(
            ApprovePlan(plan_hash),
            expected_version=current.version,
            idempotency_key=f"plan-approve:{plan_hash}",
        )
        self._project_plan(mission)
        return mission

    def reject_plan(self, note: str, *, target_phase: str = "CLARIFY") -> Mission:
        plan = self._read_plan()
        plan_hash = plan_content_hash(plan)
        current = self.load()
        if current.state is MissionState.DRAFTING and current.current_plan_hash == plan_hash:
            return current
        if not (current.state is MissionState.AWAITING_PLAN_DECISION and current.current_plan_hash == plan_hash):
            open_key = f"plan-open:{plan_hash}:{current.plan_revision + 1}"
            current = self.repository.dispatch(OpenPlan(plan_hash), idempotency_key=open_key)
        reject_key = hashlib.sha256(f"{plan_hash}\0{note}".encode("utf-8")).hexdigest()
        mission = self.repository.dispatch(
            RejectPlan(note),
            expected_version=current.version,
            idempotency_key=f"plan-reject:{reject_key}",
        )
        self._project_plan(mission, note=note, phase=target_phase)
        return mission

    def _inbox_decision_repository(
        self,
        item_id: str,
        *,
        decision_id: str | None = None,
        mission_id: str | None = None,
    ) -> DecisionRepository:
        from agent_lab.human_inbox import find_inbox_item
        from agent_lab.run.meta import read_run_meta

        run = read_run_meta(self.session_folder)
        item = find_inbox_item(run, item_id)
        if item is None:
            raise MissionApplicationError(f"inbox item is missing: {item_id}")
        prompt = str(item.get("prompt") or item.get("summary") or item.get("kind") or "Human decision")
        resolved_id = decision_id or item_id
        decision = new_decision(
            resolved_id, mission_id or self.session_folder.name, prompt, str(item.get("kind") or "question")
        )
        path = decision_journal_path(self.session_folder, resolved_id)
        return DecisionRepository(path, decision)

    def answer_inbox(self, item_id: str, answer: str, *, note: str | None = None) -> Mission:
        if self._mission_authority_enabled():
            return self.resolve_inbox_item(item_id, decision=answer, note=note, expected_version=0)
        from agent_lab.human_inbox import resolve_inbox_item

        repo = self._inbox_decision_repository(item_id)
        try:
            repo.answer(AnswerDecision(answer))
        except DecisionTransitionError as exc:
            raise MissionApplicationError(str(exc)) from exc
        resolve_inbox_item(self.session_folder, item_id, decision=answer, note=note, append_chat=False)
        mission = self.load()
        if mission.state is MissionState.AWAITING_HUMAN:
            from agent_lab.mission.kernel import ResolveBlock

            return self.repository.dispatch(ResolveBlock())
        return mission

    def guard_inbox_answer(
        self,
        item_id: str,
        answer: str,
        *,
        expected_version: int,
        decision_id: str | None = None,
        mission_id: str | None = None,
    ) -> None:
        """§7.3 optimistic-lock pre-flight — atomically checks + records the
        decision-answered event against the per-item decision journal so a
        stale or concurrent duplicate answer is rejected before the legacy
        ``resolve_inbox_item`` write path runs. Does not touch ``run.json``;
        callers still own the actual resolve.
        """
        if self._mission_authority_enabled():
            current = self.load()
            item = next((row for row in current.inbox_items if row.get("id") == item_id), None)
            if item is None or item.get("status") != "pending":
                raise MissionApplicationError(f"inbox item is not pending: {item_id}")
            item_version = item.get("decision_version", 0)
            if item_version != expected_version:
                raise MissionApplicationError(f"expected item version {expected_version}, got {item_version}")
            return

        repo = self._inbox_decision_repository(item_id, decision_id=decision_id, mission_id=mission_id)
        try:
            repo.answer(AnswerDecision(answer), expected_version=expected_version)
        except DecisionTransitionError as exc:
            raise MissionApplicationError(str(exc)) from exc

    def _read_plan(self) -> str:
        path = self.session_folder / "plan.md"
        if not path.is_file():
            raise MissionApplicationError(f"plan file is missing: {path}")
        plan = path.read_text(encoding="utf-8")
        if not plan.strip():
            raise MissionApplicationError("plan.md is empty")
        return plan

    def _project_plan(self, mission: Mission, *, note: str = "", phase: str | None = None) -> None:
        from agent_lab.time_utils import utc_now_iso

        if mission.state is MissionState.READY_TO_EXECUTE:
            projected = "APPROVED"
        else:
            allowed = {"CLARIFY", "REFINE", "DRAFT"}
            candidate = (phase or "CLARIFY").strip().upper()
            projected = candidate if candidate in allowed else "CLARIFY"

        current = read_run_meta(self.session_folder)
        workflow = current.get("plan_workflow")
        workflow = workflow if isinstance(workflow, dict) else {}
        if projected == "APPROVED":
            if (
                workflow.get("enabled") is True
                and workflow.get("phase") == projected
                and workflow.get("plan_hash_at_approval") == mission.approved_plan_hash
                and bool(workflow.get("approved_at"))
                and bool(workflow.get("approved_by"))
            ):
                return
        elif (
            workflow.get("enabled") is True
            and workflow.get("phase") == projected
            and (not note or workflow.get("last_reject_note") == note.strip()[:500])
        ):
            return

        def update(run: RunState) -> RunState:
            if projected == "APPROVED":
                updated = apply_plan_substate_patch(
                    run,
                    phase=projected,
                    plan_hash_at_approval=mission.approved_plan_hash,
                    approved_at=utc_now_iso(),
                    approved_by="human",
                    pop_fields=("last_reject_note", "notice", "last_plan_gate"),
                )
            else:
                updated = apply_plan_substate_patch(
                    run,
                    phase=projected,
                    last_reject_note=note.strip()[:500],
                    pop_fields=("notice", "last_plan_gate"),
                )
            return RunState.from_memory(updated)

        patch_run_meta(self.session_folder, update)
