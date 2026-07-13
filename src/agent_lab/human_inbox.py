"""Human Inbox — run.json items, resolve/wait, MCP bridge helpers."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.run.state import RunStateLike
from agent_lab.time_utils import utc_now_iso as _now_iso

InboxKind = Literal[
    "question",
    "build",
    "skill_draft",
    "autonomy",
    "correction_rule",
    "retry_diagnosis",
    "drift_audit",
    "rule_sync",
    "harness_patch",
]
InboxStatus = Literal["pending", "resolved", "deferred", "superseded", "rejected", "timeout"]

DEFAULT_INBOX_TIMEOUT_SEC = int(os.getenv("AGENT_LAB_INBOX_TIMEOUT_SEC", "1800"))
INBOX_POLL_SEC = float(os.getenv("AGENT_LAB_INBOX_POLL_SEC", "0.25"))


def _new_id(prefix: str = "inbox") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def inbox_items(run: RunStateLike) -> list[dict[str, Any]]:
    raw = run.get("human_inbox")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def compute_inbox_pending(run: RunStateLike) -> bool:
    return any(item.get("status") == "pending" for item in inbox_items(run))


def pending_inbox_items(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in inbox_items(run) if item.get("status") == "pending"]


def find_inbox_item(run: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for item in inbox_items(run):
        if item.get("id") == item_id:
            return item
    return None


def latest_mcp_build_item(run: dict[str, Any]) -> dict[str, Any] | None:
    """Most recent execute-lane ``propose_build`` inbox item, if any."""
    found: dict[str, Any] | None = None
    for item in inbox_items(run):
        if item.get("source") == "mcp_propose_build":
            found = item
    return found


def execute_inbox_build_go(folder: Path) -> bool:
    """True when Human GO was received for the latest MCP ``propose_build`` item."""
    item = latest_mcp_build_item(read_run_meta(folder))
    if not item or item.get("status") == "pending":
        return False
    return build_propose_build_tool_result(item).get("decision") == "go"


def has_pending_question(run: dict[str, Any]) -> bool:
    return any(item.get("status") == "pending" and item.get("kind") == "question" for item in inbox_items(run))


def format_human_decision(item: dict[str, Any]) -> str:
    item_id = str(item.get("id") or "")
    choice = item.get("resolved_choice")
    if choice is None and item.get("resolved_selected"):
        selected = item.get("resolved_selected")
        if isinstance(selected, list):
            choice = ",".join(str(x) for x in selected)
    if choice is None:
        choice = item.get("resolved_decision") or ""
    note = str(item.get("resolved_note") or "").replace("\n", " ").strip()
    return f"[HUMAN-DECISION: id={item_id} choice={choice} note={note}]"


def public_inbox_payload(run: dict[str, Any]) -> dict[str, Any]:
    items = inbox_items(run)
    pending = [item for item in items if item.get("status") == "pending"]
    return {
        "human_inbox": items,
        "inbox_pending": compute_inbox_pending(run),
        "pending_count": len(pending),
        "pending_questions": sum(1 for item in pending if item.get("kind") == "question"),
        "pending_builds": sum(1 for item in pending if item.get("kind") == "build"),
        "pending_skill_drafts": sum(1 for item in pending if item.get("kind") == "skill_draft"),
        "pending_autonomy": sum(1 for item in pending if item.get("kind") == "autonomy"),
    }


def _read_session_meta(folder: Path) -> dict[str, Any]:
    meta_path = folder / "meta.json"
    if not meta_path.is_file():
        return {}
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _session_topic(folder: Path, meta: dict[str, Any]) -> str:
    topic_file = folder / "topic.txt"
    if topic_file.is_file():
        try:
            return topic_file.read_text(encoding="utf-8").strip() or folder.name
        except OSError:
            pass
    topic = meta.get("topic")
    return str(topic).strip() if topic else folder.name


def build_inbox_summary(
    sessions_root: Path,
    *,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Aggregate pending Human Inbox items across non-fixture sessions."""
    if not sessions_root.is_dir():
        return {
            "total_pending": 0,
            "pending_questions": 0,
            "pending_builds": 0,
            "sessions": [],
        }

    sessions: list[dict[str, Any]] = []
    total_pending = 0
    total_questions = 0
    total_builds = 0

    for folder in sorted(sessions_root.iterdir(), reverse=True):
        if not folder.is_dir() or folder.name.startswith(".") or folder.name.startswith("_"):
            continue
        meta = _read_session_meta(folder)
        if bool(meta.get("archived")) != include_archived:
            continue
        run_path = folder / "run.json"
        if not run_path.is_file():
            continue
        try:
            run = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(run, dict):
            continue
        payload = public_inbox_payload(run)
        pending_count = int(payload.get("pending_count") or 0)
        if pending_count <= 0:
            continue
        pending_questions = int(payload.get("pending_questions") or 0)
        pending_builds = int(payload.get("pending_builds") or 0)
        total_pending += pending_count
        total_questions += pending_questions
        total_builds += pending_builds
        sessions.append(
            {
                "session_id": folder.name,
                "topic": _session_topic(folder, meta),
                "pending_count": pending_count,
                "pending_questions": pending_questions,
                "pending_builds": pending_builds,
                "inbox_pending": True,
            }
        )

    return {
        "total_pending": total_pending,
        "pending_questions": total_questions,
        "pending_builds": total_builds,
        "sessions": sessions,
    }


def _sync_inbox_flag(run: dict[str, Any]) -> dict[str, Any]:
    run["inbox_pending"] = compute_inbox_pending(run)
    return run


def new_inbox_item(
    *,
    kind: InboxKind,
    source: str,
    prompt: str,
    options: list[dict[str, Any]] | None = None,
    multi_select: bool = False,
    action_ref: str | None = None,
    summary: str | None = None,
    risks: list[str] | None = None,
    mcp_call_id: str | None = None,
    session_id: str | None = None,
    human_turn_id: int | None = None,
    context_ref: str | None = None,
    trigger: str | None = None,
    refs: list[str] | None = None,
    harvest_key: str | None = None,
    plan_revision: str | None = None,
    caller_agent: str | None = None,
) -> dict[str, Any]:
    """Build a pending inbox item dict (no I/O).

    Shared by ``create_inbox_item`` (folder patch) and discuss harvest
    (in-memory ``run_meta`` mutation, see ``inbox_harvest``).
    """
    return {
        "id": _new_id(),
        "kind": kind,
        "source": source,
        "status": "pending",
        "prompt": prompt,
        "summary": summary,
        "options": options or [],
        "multi_select": bool(multi_select),
        "action_ref": action_ref,
        "risks": risks or [],
        "refs": refs or [],
        "trigger": trigger,
        "harvest_key": harvest_key,
        "plan_revision": plan_revision,
        "context_ref": context_ref,
        "mcp_call_id": mcp_call_id,
        "session_id": session_id,
        "human_turn_id": human_turn_id,
        "caller_agent": str(caller_agent).strip().lower() if caller_agent else None,
        "created_at": _now_iso(),
        "resolved_at": None,
        "resolved_choice": None,
        "resolved_selected": None,
        "resolved_decision": None,
        "resolved_note": None,
    }


def append_inbox_item(run: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    """Append a built item to an in-memory run dict (caller persists)."""
    items = inbox_items(run)
    items.append(item)
    run["human_inbox"] = items
    return _sync_inbox_flag(run)


def create_inbox_item(
    folder: Path,
    *,
    kind: InboxKind,
    source: str,
    prompt: str,
    options: list[dict[str, Any]] | None = None,
    multi_select: bool = False,
    action_ref: str | None = None,
    summary: str | None = None,
    risks: list[str] | None = None,
    mcp_call_id: str | None = None,
    session_id: str | None = None,
    human_turn_id: int | None = None,
    context_ref: str | None = None,
    trigger: str | None = None,
    refs: list[str] | None = None,
    harvest_key: str | None = None,
    caller_agent: str | None = None,
) -> dict[str, Any]:
    if kind == "build" and has_pending_question(read_run_meta(folder)):
        raise ValueError("pending question blocks build item creation")

    item = new_inbox_item(
        kind=kind,
        source=source,
        prompt=prompt,
        options=options,
        multi_select=multi_select,
        action_ref=action_ref,
        summary=summary,
        risks=risks,
        mcp_call_id=mcp_call_id,
        session_id=session_id,
        human_turn_id=human_turn_id,
        context_ref=context_ref,
        trigger=trigger,
        refs=refs,
        harvest_key=harvest_key,
        caller_agent=caller_agent,
    )

    from agent_lab.mission.dual_write import (
        commit_inbox_creation,
        inbox_write_authority_enabled,
        mirror_inbox_creation,
    )

    if inbox_write_authority_enabled(folder):
        bridge = commit_inbox_creation(
            folder,
            item_id=item["id"],
            kind=kind,
            reason=summary or prompt,
        )
        if bridge.get("mirrored") is not True:
            raise ValueError(f"mission inbox commit failed: {bridge.get('reason') or 'unknown'}")

    patch_run_meta(folder, lambda run: append_inbox_item(run, item))
    try:
        from agent_lab.room.live_log import append_live_room_event

        append_live_room_event(
            folder,
            "inbox_pending",
            {"item_id": item["id"], "kind": kind, "source": source},
        )
    except Exception:
        pass
    try:
        from agent_lab.gateway.adapters import fan_out_gateway_notify

        fan_out_gateway_notify(
            "inbox_pending",
            {"session_id": folder.name, "item": item},
        )
    except Exception:
        pass
    if not inbox_write_authority_enabled(folder):
        try:
            mirror_inbox_creation(folder, item_id=item["id"], kind=kind, reason=summary or prompt)
        except Exception:
            pass
    return item


def fan_out_inbox_item(session_id: str, item: dict[str, Any]) -> None:
    """Notify gateway adapters for a newly appended inbox item (harvest path)."""
    try:
        from agent_lab.gateway.adapters import fan_out_gateway_notify

        fan_out_gateway_notify(
            "inbox_pending",
            {"session_id": session_id, "item": item},
        )
    except Exception:
        pass


def supersede_pending_inbox(folder: Path, *, human_turn_id: int | None = None) -> int:
    ts = _now_iso()
    count = 0
    superseded_ids: list[str] = []

    def _supersede(run: dict[str, Any]) -> dict[str, Any]:
        nonlocal count
        for item in inbox_items(run):
            if item.get("status") != "pending":
                continue
            item_id = str(item.get("id") or "")
            item["status"] = "superseded"
            item["superseded_at"] = ts
            if human_turn_id is not None:
                item["superseded_human_turn_id"] = human_turn_id
            count += 1
            if item_id:
                superseded_ids.append(item_id)
        run["human_inbox"] = inbox_items(run)
        return _sync_inbox_flag(run)

    patch_run_meta(folder, _supersede)
    if superseded_ids:
        try:
            from agent_lab.mission.dual_write import close_gates_for_inbox_ids

            close_gates_for_inbox_ids(folder, superseded_ids, answer="superseded")
        except Exception:
            pass
    return count


def resolve_inbox_item(
    folder: Path,
    item_id: str,
    *,
    status: InboxStatus = "resolved",
    selected: list[str] | None = None,
    decision: str | None = None,
    note: str | None = None,
    append_chat: bool = True,
) -> dict[str, Any]:
    resolved_at = _now_iso()
    updated: dict[str, Any] | None = None

    def _resolve(run: dict[str, Any]) -> dict[str, Any]:
        nonlocal updated
        item = find_inbox_item(run, item_id)
        if item is None:
            raise ValueError(f"inbox item not found: {item_id}")
        if item.get("status") != "pending":
            raise ValueError(f"inbox item not pending: {item_id}")

        item["status"] = status
        item["resolved_at"] = resolved_at
        if selected is not None:
            item["resolved_selected"] = selected
            item["resolved_choice"] = ",".join(selected) if selected else ""
        if decision is not None:
            item["resolved_decision"] = decision
            item["resolved_choice"] = decision
        if note is not None:
            item["resolved_note"] = note
        if (
            note
            and not selected
            and decision is None
            and item.get("kind") == "question"
            and not item.get("resolved_choice")
        ):
            item["resolved_choice"] = "freeform"
            item["resolved_selected"] = ["freeform"]

        run["human_inbox"] = inbox_items(run)
        updated = dict(item)
        from agent_lab.inbox.harvest import clear_inbox_fork_grace

        clear_inbox_fork_grace(run)
        return _sync_inbox_flag(run)

    patch_run_meta(folder, _resolve)
    if updated is None:
        raise ValueError(f"inbox item not found: {item_id}")

    if append_chat and status in ("resolved", "deferred"):
        _append_decision_to_chat(folder, updated)

    if updated.get("kind") == "skill_draft" and status in ("resolved", "rejected", "superseded"):
        try:
            from agent_lab.skill_drafts import handle_skill_draft_inbox_resolve

            handle_skill_draft_inbox_resolve(
                folder,
                updated,
                selected=selected,
                status=status,
            )
        except ValueError:
            pass

    if updated.get("kind") == "correction_rule" and status in ("resolved", "rejected", "superseded"):
        try:
            from agent_lab.correction_harvester import handle_correction_rule_inbox_resolve

            handle_correction_rule_inbox_resolve(
                folder,
                updated,
                selected=selected,
                status=status,
            )
        except Exception:  # fail-open: rule promotion must never block inbox resolve
            import logging

            logging.getLogger(__name__).warning("correction_rule inbox resolve failed", exc_info=True)

    if updated.get("kind") == "retry_diagnosis" and status in ("resolved", "rejected", "superseded"):
        try:
            from agent_lab.room.retry import handle_retry_diagnosis_inbox_resolve

            handle_retry_diagnosis_inbox_resolve(
                folder,
                updated,
                selected=selected,
                status=status,
            )
        except Exception:  # fail-open: force-ack bookkeeping must never block inbox resolve
            import logging

            logging.getLogger(__name__).warning("retry_diagnosis inbox resolve failed", exc_info=True)

    if updated.get("kind") == "drift_audit" and status in ("resolved", "rejected", "superseded"):
        try:
            from agent_lab.drift_audit import handle_drift_audit_inbox_resolve

            handle_drift_audit_inbox_resolve(
                folder,
                updated,
                selected=selected,
                status=status,
            )
        except Exception:  # fail-open: baseline re-snapshot must never block inbox resolve
            import logging

            logging.getLogger(__name__).warning("drift_audit inbox resolve failed", exc_info=True)

    if updated.get("kind") == "rule_sync" and status in ("resolved", "rejected", "superseded"):
        try:
            from agent_lab.rule_sync import handle_rule_sync_inbox_resolve

            handle_rule_sync_inbox_resolve(
                folder,
                updated,
                selected=selected,
                status=status,
            )
        except Exception:  # fail-open: external file sync must never block inbox resolve
            import logging

            logging.getLogger(__name__).warning("rule_sync inbox resolve failed", exc_info=True)

    if updated.get("kind") == "harness_patch" and status in ("resolved", "rejected", "superseded"):
        try:
            from agent_lab.merge_gate import handle_harness_patch_resolve

            handle_harness_patch_resolve(
                folder,
                updated,
                selected=selected,
                status=status,
            )
        except Exception:  # fail-open: merge failure must never corrupt inbox state
            import logging

            logging.getLogger(__name__).warning("harness_patch inbox resolve failed", exc_info=True)

    if updated.get("kind") == "autonomy" and status == "resolved":
        try:
            if updated.get("source") == "autonomy_promotion":
                from agent_lab.autonomy_promotion import handle_autonomy_promotion_resolve

                handle_autonomy_promotion_resolve(folder, updated, selected=selected)
            else:
                from agent_lab.autonomy_inbox import handle_autonomy_inbox_resolve

                handle_autonomy_inbox_resolve(folder, updated, selected=selected)
        except ValueError:
            pass

    from agent_lab.plan.workflow import tick_plan_workflow_after_inbox_resolve

    from agent_lab.session.clarifier import sync_clarifier_answers_from_inbox

    sync_clarifier_answers_from_inbox(folder)
    from agent_lab.plan.workflow import ensure_plan_clarify_inbox_question

    ensure_plan_clarify_inbox_question(folder)
    tick_plan_workflow_after_inbox_resolve(folder)

    return updated


def _append_decision_to_chat(folder: Path, item: dict[str, Any]) -> None:
    import json

    chat_path = folder / "chat.jsonl"
    line = format_human_decision(item)
    record = {
        "role": "human",
        "agent": None,
        "content": line,
        "ts": _now_iso(),
    }
    with chat_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_ask_human_tool_result(item: dict[str, Any]) -> dict[str, Any]:
    status = item.get("status")
    if status == "timeout":
        return {
            "status": "timeout",
            "selected": [],
            "freeform": None,
            "inbox_item_id": item.get("id"),
            "resolved_at": item.get("resolved_at"),
        }
    if status == "superseded":
        return {
            "status": "superseded",
            "selected": [],
            "freeform": None,
            "inbox_item_id": item.get("id"),
            "resolved_at": item.get("resolved_at"),
        }
    selected = item.get("resolved_selected") or []
    if not selected and item.get("resolved_choice"):
        selected = [part.strip() for part in str(item["resolved_choice"]).split(",") if part.strip()]
    return {
        "selected": selected,
        "freeform": item.get("resolved_note"),
        "inbox_item_id": item.get("id"),
        "resolved_at": item.get("resolved_at"),
    }


def build_propose_build_tool_result(item: dict[str, Any]) -> dict[str, Any]:
    status = item.get("status")
    decision = item.get("resolved_decision") or item.get("resolved_choice") or "defer"
    if status == "timeout":
        return {
            "decision": "defer",
            "status": "timeout",
            "note": item.get("resolved_note"),
            "inbox_item_id": item.get("id"),
            "resolved_at": item.get("resolved_at"),
        }
    if status == "superseded":
        return {
            "decision": "defer",
            "status": "superseded",
            "note": item.get("resolved_note"),
            "inbox_item_id": item.get("id"),
            "resolved_at": item.get("resolved_at"),
        }
    if status == "rejected":
        decision = "reject"
    elif status == "deferred":
        decision = "defer"
    elif status == "resolved" and decision not in ("go", "defer", "reject"):
        decision = "go"
    return {
        "decision": decision,
        "note": item.get("resolved_note"),
        "inbox_item_id": item.get("id"),
        "resolved_at": item.get("resolved_at"),
    }


def tool_result_for_item(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("kind") == "build":
        return build_propose_build_tool_result(item)
    return build_ask_human_tool_result(item)


def wait_for_inbox_item(
    folder: Path,
    item_id: str,
    *,
    timeout_sec: int | None = None,
    poll_sec: float | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + (timeout_sec or DEFAULT_INBOX_TIMEOUT_SEC)
    interval = poll_sec if poll_sec is not None else INBOX_POLL_SEC

    while time.monotonic() < deadline:
        from agent_lab.run.control import RoomRunCancelled, check_cancelled

        try:
            check_cancelled()
        except RoomRunCancelled:
            raise
        run = read_run_meta(folder)
        item = find_inbox_item(run, item_id)
        if item is None:
            raise ValueError(f"inbox item not found: {item_id}")
        status = item.get("status")
        if status != "pending":
            return tool_result_for_item(item)
        from agent_lab.backoff_policy import wait as _backoff_wait

        _backoff_wait(1, base_sec=interval)

    def _timeout(run: dict[str, Any]) -> dict[str, Any]:
        item = find_inbox_item(run, item_id)
        if item and item.get("status") == "pending":
            item["status"] = "timeout"
            item["resolved_at"] = _now_iso()
            item["resolved_note"] = "human inbox timeout"
            run["human_inbox"] = inbox_items(run)
        return _sync_inbox_flag(run)

    patch_run_meta(folder, _timeout)
    run = read_run_meta(folder)
    item = find_inbox_item(run, item_id)
    if item is None:
        raise ValueError(f"inbox item not found: {item_id}")
    return tool_result_for_item(item)


def create_mcp_question_and_wait(
    folder: Path,
    *,
    question: str,
    options: list[dict[str, Any]],
    multi_select: bool = False,
    context_ref: str | None = None,
    mcp_call_id: str | None = None,
    caller_agent: str | None = None,
    policy_lane: str | None = None,
) -> dict[str, Any]:
    from agent_lab.inbox.mcp_policy import enforce_mcp_ask_human_policy

    enforce_mcp_ask_human_policy(
        folder,
        caller_agent=caller_agent,
        policy_lane=policy_lane,
    )
    if len(options) < 2:
        raise ValueError("ask_human requires at least 2 options")
    from agent_lab.inbox.mcp_policy import _caller_agent_from_env

    resolved_caller = _caller_agent_from_env(caller_agent) or None
    item = create_inbox_item(
        folder,
        kind="question",
        source="mcp_ask_human",
        prompt=question,
        options=options,
        multi_select=multi_select,
        context_ref=context_ref,
        mcp_call_id=mcp_call_id,
        caller_agent=resolved_caller,
    )
    return wait_for_inbox_item(folder, item["id"])


def create_mcp_build_and_wait(
    folder: Path,
    *,
    summary: str,
    action_ref: str,
    risks: list[str] | None = None,
    mcp_call_id: str | None = None,
    caller_agent: str | None = None,
) -> dict[str, Any]:
    from agent_lab.inbox.mcp_policy import enforce_mcp_propose_build_policy
    from agent_lab.room.turn_policy import stamp_pending_skill_intent, turn_policy_enabled

    enforce_mcp_propose_build_policy(folder, caller_agent=caller_agent)
    if turn_policy_enabled():
        stamp_pending_skill_intent(folder, "propose_build")
    item = create_inbox_item(
        folder,
        kind="build",
        source="mcp_propose_build",
        prompt=summary,
        summary=summary,
        action_ref=action_ref,
        risks=risks or [],
        mcp_call_id=mcp_call_id,
    )
    return wait_for_inbox_item(folder, item["id"])
