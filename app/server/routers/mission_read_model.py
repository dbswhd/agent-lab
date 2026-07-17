from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from typing_extensions import NotRequired, TypedDict

from agent_lab.mission.application import MissionApplication
from agent_lab.mission.journal import JournalCorruptionError, MissionJournal
from agent_lab.mission.read_model import (
    MissionReadModel,
    build_legacy_composites,
    build_read_model,
    session_run_for_read_model,
)
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
    operational_status: str | None
    open_execution_gates: list[dict[str, Any]]
    legacy_phase: str | None
    plan: NotRequired[dict[str, Any] | None]
    work_phase: NotRequired[str | None]
    mission_overview: NotRequired[dict[str, Any] | None]
    inbox_summary: NotRequired[dict[str, Any] | None]
    inbox_items: NotRequired[list[dict[str, Any]]]


def _with_decision_versions(items: list[dict[str, Any]], folder: Path) -> list[dict[str, Any]]:
    """§7.3 — attach each item's optimistic-lock ``decision_version`` (0 if never
    answered) so ``HumanInboxPanel`` can round-trip ``expected_version`` on resolve.
    ``decision_id`` is intentionally not added: it always equals the item's own
    ``id`` (see ``MissionApplication._inbox_decision_repository``'s ``decision_id
    or item_id`` fallback), so callers can send ``item.id`` as-is.
    """
    from agent_lab.mission.decision_repository import load_decision_version

    enriched: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        item_id = row.get("id")
        version = 0
        if isinstance(item_id, str) and item_id:
            try:
                version = load_decision_version(folder, item_id, mission_id=folder.name)
            except Exception:
                version = 0
        row["decision_version"] = version
        enriched.append(row)
    return enriched


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


def _legacy_phase(folder: Path, run: dict[str, Any] | None = None) -> str | None:
    meta = run if run is not None else read_run_meta(folder)
    mission_loop = meta.get("mission_loop")
    if not isinstance(mission_loop, dict):
        return None
    phase = mission_loop.get("phase")
    return phase if isinstance(phase, str) else None


def _composite_dict(model: MissionReadModel) -> dict[str, Any]:
    plan = model.plan
    overview = model.mission_overview
    inbox = model.inbox_summary
    return {
        "plan": (
            {
                "phase": plan.phase,
                "hash": plan.hash,
                "approved_hash": plan.approved_hash,
                "pending_approval": plan.pending_approval,
            }
            if plan is not None
            else None
        ),
        "work_phase": model.work_phase,
        "mission_overview": (
            {
                "phase_label": overview.phase_label,
                "paused": overview.paused,
                "circuit_breaker": overview.circuit_breaker,
                "pending_inbox_count": overview.pending_inbox_count,
            }
            if overview is not None
            else None
        ),
        "inbox_summary": (
            {
                "pending_count": inbox.pending_count,
                "pending_questions": inbox.pending_questions,
                "pending_builds": inbox.pending_builds,
            }
            if inbox is not None
            else None
        ),
        "inbox_items": list(model.inbox_items),
    }


def _payload(
    session_id: str,
    model: MissionReadModel,
    *,
    legacy_phase: str | None,
    folder: Path,
    run: dict[str, Any] | None,
) -> MissionReadModelPayload:
    composites = _composite_dict(model)
    payload: MissionReadModelPayload = {
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
        "operational_status": model.operational_status.value,
        "open_execution_gates": [{"gate_id": g.gate_id, "kind": g.kind} for g in model.open_execution_gates],
        "legacy_phase": legacy_phase,
        "plan": composites["plan"],
        "work_phase": composites["work_phase"],
        "mission_overview": composites["mission_overview"],
        "inbox_summary": composites["inbox_summary"],
        "inbox_items": _with_decision_versions(composites["inbox_items"], folder),
    }
    if not _payload_integrity_ok(payload, folder=folder, run=run):
        return _legacy_payload(session_id, folder)
    return payload


def folder_or_404(session_id: str) -> Path:
    from app.server.deps import session_folder_or_404

    return session_folder_or_404(session_id)


def _payload_integrity_ok(
    payload: MissionReadModelPayload,
    *,
    folder: Path,
    run: dict[str, Any] | None,
) -> bool:
    """§8.1: parsing boundary validation. Fail closed to legacy on any structural violation."""
    event_cursor = payload.get("event_cursor")
    if not isinstance(event_cursor, int) or event_cursor < 0:
        return False
    if event_cursor != _expected_event_cursor(folder):
        return False
    if run is not None:
        run_cursor = run.get("mission_loop", {}).get("event_cursor")
        if run_cursor is not None and event_cursor != run_cursor:
            return False
    if not payload.get("mission_id"):
        return False
    if payload.get("operational_status") is None:
        return False
    if not isinstance(payload.get("inbox_items"), list):
        return False
    return True


def _expected_event_cursor(folder: Path) -> int:
    """Count events in the journal, not physical lines.

    ``MissionJournal.append()`` can write >1 event as a single ``batch``
    record, so a raw line count undercounts the true cursor whenever a
    multi-event dispatch (e.g. ``MissionRepository.decide_plan``) has run.
    Uses ``recover_tail()`` — the same self-healing read ``MissionApplication``
    uses to derive ``model.version`` — so a torn trailing write doesn't
    disagree with the event_cursor it's meant to validate.
    """
    journal = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal.is_file():
        return 0
    try:
        return len(MissionJournal(journal).recover_tail())
    except JournalCorruptionError:
        # Corruption must fail closed to legacy, never coincidentally match a
        # fresh mission's event_cursor (0), so -1 rather than 0 here.
        return -1


def _legacy_payload(session_id: str, folder: Path) -> MissionReadModelPayload:
    run = session_run_for_read_model(folder)
    composites = build_legacy_composites(run)
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
        "operational_status": None,
        "open_execution_gates": [],
        "legacy_phase": _legacy_phase(folder, run),
        "plan": composites["plan"],
        "work_phase": composites["work_phase"],
        "mission_overview": composites["mission_overview"],
        "inbox_summary": composites["inbox_summary"],
        "inbox_items": _with_decision_versions(composites["inbox_items"], folder),
    }


@router.get("/sessions/{session_id}/mission/read-model")
def get_mission_read_model(session_id: str) -> MissionReadModelPayload:
    folder = session_folder_or_404(session_id)
    journal_path = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal_path.is_file():
        return _legacy_payload(session_id, folder)
    run = session_run_for_read_model(folder)
    goal = _goal_from_run(folder)
    legacy = _legacy_phase(folder, run)
    try:
        model = build_read_model(MissionApplication(folder, goal).load(), legacy_phase=legacy, run=run)
    except Exception:
        return _legacy_payload(session_id, folder)
    return _payload(session_id, model, legacy_phase=model.legacy_phase, folder=folder, run=run)
