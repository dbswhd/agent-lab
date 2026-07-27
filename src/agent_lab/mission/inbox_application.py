from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from agent_lab.env_flags import is_truthy
from agent_lab.mission.errors import MissionTransitionError
from agent_lab.mission.kernel import Mission, OpenInboxItem, ResolveInboxItem
from agent_lab.mission.messages import JsonValue
from agent_lab.time_utils import utc_now_iso

if TYPE_CHECKING:
    from agent_lab.mission.application import MissionApplication


class MissionInboxAuthorityError(ValueError):
    pass


def mission_authority_enabled(folder: Path) -> bool:
    raw = (os.getenv("AGENT_LAB_MISSION_AUTHORITY_SESSIONS") or "").strip()
    cohort = frozenset(item.strip() for item in raw.split(",") if item.strip())
    return is_truthy(os.getenv("AGENT_LAB_MISSION_AUTHORITY")) and bool(cohort) and folder.name in cohort


def open_inbox_item(application: MissionApplication, item: Mapping[str, JsonValue]) -> Mission:
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id:
        raise MissionInboxAuthorityError("inbox item id is required")
    current = application.load()
    return application.repository.dispatch(
        OpenInboxItem(item),
        expected_version=current.version,
        idempotency_key=f"inbox-open:{item_id}",
    )


def resolve_inbox_item(
    application: MissionApplication,
    item_id: str,
    *,
    status: str = "resolved",
    selected: list[str] | None = None,
    decision: str | None = None,
    note: str | None = None,
    expected_version: int | None = None,
) -> Mission:
    current = application.load()
    item = next((row for row in current.inbox_items if row.get("id") == item_id), None)
    if item is None:
        raise MissionInboxAuthorityError(f"inbox item is missing: {item_id}")
    item_version = item.get("decision_version", 0)
    if not isinstance(item_version, int) or isinstance(item_version, bool):
        raise MissionInboxAuthorityError(f"inbox item version is invalid: {item_id}")
    if expected_version is not None and item_version != expected_version:
        raise MissionInboxAuthorityError(f"expected item version {expected_version}, got {item_version}")
    if item.get("status") != "pending":
        raise MissionInboxAuthorityError(f"inbox item is not pending: {item_id}")

    updated = dict(item)
    updated["status"] = status
    updated["resolved_at"] = utc_now_iso()
    updated["decision_version"] = item_version + 1
    if selected is not None:
        selected_values: list[JsonValue] = [value for value in selected]
        updated["resolved_selected"] = selected_values
        updated["resolved_choice"] = ",".join(selected) if selected else ""
    if decision is not None:
        updated["resolved_decision"] = decision
        updated["resolved_choice"] = decision
    if note is not None:
        updated["resolved_note"] = note
    if note and not selected and decision is None and item.get("kind") == "question":
        updated["resolved_choice"] = "freeform"
        updated["resolved_selected"] = ["freeform"]
    try:
        return application.repository.dispatch(
            ResolveInboxItem(item_id, updated),
            expected_version=current.version,
            idempotency_key=f"inbox-resolve:{item_id}:{item_version + 1}:{updated.get('resolved_choice', '')}",
        )
    except (MissionTransitionError, OSError, ValueError) as exc:
        raise MissionInboxAuthorityError(str(exc)) from exc
