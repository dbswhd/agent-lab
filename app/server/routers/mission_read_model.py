from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict

from fastapi import APIRouter

from agent_lab.mission.application import MissionApplication
from agent_lab.mission.read_model import MissionReadModel, build_read_model
from agent_lab.run.meta import read_run_meta

from app.server.deps import session_folder_or_404

router = APIRouter(prefix="/api")


class MissionReadModelPayload(TypedDict):
    session_id: str
    migrated: bool
    source: Literal["mission_journal", "legacy"]
    mission_id: str | None
    goal: str | None
    state: str | None
    version: int | None
    plan_revision: int | None
    plan_hash: str | None
    approved_plan_hash: str | None
    repair_attempt: int | None
    max_repair_attempts: int | None
    oracle_verdict: str | None
    next_action: str
    event_cursor: int
    legacy_phase: str | None


def _goal_from_run(folder: Path) -> str:
    run = read_run_meta(folder)
    for key in ("goal", "topic"):
        value = run.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    topic_path = folder / "topic.txt"
    if topic_path.is_file():
        topic = topic_path.read_text(encoding="utf-8").strip()
        if topic:
            return topic
    return folder.name


def _legacy_phase(folder: Path) -> str | None:
    mission_loop = read_run_meta(folder).get("mission_loop")
    if not isinstance(mission_loop, dict):
        return None
    phase = mission_loop.get("phase")
    return phase if isinstance(phase, str) else None


def _payload(session_id: str, model: MissionReadModel, *, legacy_phase: str | None) -> MissionReadModelPayload:
    return {
        "session_id": session_id,
        "migrated": True,
        "source": "mission_journal",
        "mission_id": model.mission_id,
        "goal": model.goal,
        "state": model.state.value,
        "version": model.version,
        "plan_revision": model.plan_revision,
        "plan_hash": model.plan_hash,
        "approved_plan_hash": model.approved_plan_hash,
        "repair_attempt": model.repair_attempt,
        "max_repair_attempts": model.max_repair_attempts,
        "oracle_verdict": model.oracle_verdict.value if model.oracle_verdict is not None else None,
        "next_action": model.next_action,
        "event_cursor": model.event_cursor,
        "legacy_phase": legacy_phase,
    }


def _legacy_payload(session_id: str, folder: Path) -> MissionReadModelPayload:
    return {
        "session_id": session_id,
        "migrated": False,
        "source": "legacy",
        "mission_id": None,
        "goal": _goal_from_run(folder),
        "state": None,
        "version": None,
        "plan_revision": None,
        "plan_hash": None,
        "approved_plan_hash": None,
        "repair_attempt": None,
        "max_repair_attempts": None,
        "oracle_verdict": None,
        "next_action": "legacy_route",
        "event_cursor": 0,
        "legacy_phase": _legacy_phase(folder),
    }


@router.get("/sessions/{session_id}/mission/read-model")
def get_mission_read_model(session_id: str) -> MissionReadModelPayload:
    folder = session_folder_or_404(session_id)
    journal_path = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal_path.is_file():
        return _legacy_payload(session_id, folder)
    goal = _goal_from_run(folder)
    model = build_read_model(MissionApplication(folder, goal).load(), legacy_phase=_legacy_phase(folder))
    return _payload(session_id, model, legacy_phase=model.legacy_phase)
