from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from agent_lab.mission.decision_queue import AnswerDecision, new_decision
from agent_lab.mission.decision_repository import DecisionRepository
from agent_lab.mission.kernel import ApprovePlan, Mission, MissionState, OpenPlan, RejectPlan
from agent_lab.mission.repository import MissionRepository
from agent_lab.plan.pending import plan_content_hash
from agent_lab.run.meta import patch_run_meta
from agent_lab.run.state import RunState
from agent_lab.plan.workflow_state import apply_plan_substate_patch


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

    def approve_plan(self) -> Mission:
        plan = self._read_plan()
        current = self.load()
        plan_hash = plan_content_hash(plan)
        if current.state is MissionState.READY_TO_EXECUTE and current.approved_plan_hash == plan_hash:
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

    def reject_plan(self, note: str) -> Mission:
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
        self._project_plan(mission, note=note)
        return mission

    def answer_inbox(self, item_id: str, answer: str, *, note: str | None = None) -> Mission:
        from agent_lab.human_inbox import find_inbox_item, resolve_inbox_item
        from agent_lab.run.meta import read_run_meta

        run = read_run_meta(self.session_folder)
        item = find_inbox_item(run, item_id)
        if item is None:
            raise MissionApplicationError(f"inbox item is missing: {item_id}")
        prompt = str(item.get("prompt") or item.get("summary") or item.get("kind") or "Human decision")
        decision = new_decision(item_id, self.session_folder.name, prompt, str(item.get("kind") or "question"))
        path = self.session_folder / ".agent-lab" / "decisions" / f"{hashlib.sha256(item_id.encode()).hexdigest()}.jsonl"
        DecisionRepository(path, decision).answer(AnswerDecision(answer))
        resolve_inbox_item(self.session_folder, item_id, decision=answer, note=note, append_chat=False)
        mission = self.load()
        if mission.state is MissionState.AWAITING_HUMAN:
            from agent_lab.mission.kernel import ResolveBlock

            return self.repository.dispatch(ResolveBlock())
        return mission

    def _read_plan(self) -> str:
        path = self.session_folder / "plan.md"
        if not path.is_file():
            raise MissionApplicationError(f"plan file is missing: {path}")
        plan = path.read_text(encoding="utf-8")
        if not plan.strip():
            raise MissionApplicationError("plan.md is empty")
        return plan

    def _project_plan(self, mission: Mission, *, note: str = "") -> None:
        phase = "APPROVED" if mission.state is MissionState.READY_TO_EXECUTE else "CLARIFY"

        def update(run: RunState) -> RunState:
            if phase == "APPROVED":
                updated = apply_plan_substate_patch(
                    run,
                    phase=phase,
                    plan_hash_at_approval=mission.approved_plan_hash,
                    pop_fields=("last_reject_note",),
                )
            else:
                updated = apply_plan_substate_patch(
                    run,
                    phase=phase,
                    last_reject_note=note.strip()[:500],
                )
            return RunState.from_memory(updated)

        patch_run_meta(self.session_folder, update)
