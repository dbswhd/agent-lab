from __future__ import annotations

from pathlib import Path

from agent_lab.mission.event_codec import decode_event, encode_event
from agent_lab.mission.journal import MissionJournal
from agent_lab.mission.kernel import Mission, MissionCommand, apply_event, decide, new_mission
from agent_lab.mission.plan_bridge import PlanApprovalDecision, plan_decision_events


class MissionRepository:
    def __init__(self, journal_path: Path, mission_id: str, goal: str) -> None:
        self._journal = MissionJournal(journal_path, mission_id=mission_id)
        self._mission_id = mission_id
        self._goal = goal

    def load(self) -> Mission:
        mission = new_mission(self._mission_id, self._goal)
        for stored in self._journal.recover_tail():
            mission = apply_event(mission, decode_event(stored))
        return mission

    def dispatch(
        self,
        command: MissionCommand,
        *,
        expected_version: int | None = None,
        idempotency_key: str | None = None,
    ) -> Mission:
        current = self.load()
        if idempotency_key is not None and self._journal.find_idempotency(idempotency_key):
            return self.load()
        events = decide(current, command, expected_version=expected_version)
        self._journal.append(
            tuple(encode_event(event) for event in events),
            expected_sequence=current.version,
            idempotency_key=idempotency_key,
        )
        for event in events:
            current = apply_event(current, event)
        return current

    def decide_plan(self, plan_md: str, decision: PlanApprovalDecision) -> Mission:
        current = self.load()
        events = plan_decision_events(current, plan_md, decision)
        self._journal.append(tuple(encode_event(event) for event in events), expected_sequence=current.version)
        for event in events:
            current = apply_event(current, event)
        return current
