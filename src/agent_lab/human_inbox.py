"""Human Inbox — run.json items, resolve/wait, MCP bridge helpers."""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_lab.run_meta import patch_run_meta, read_run_meta

InboxKind = Literal["question", "build"]
InboxStatus = Literal["pending", "resolved", "deferred", "superseded", "rejected", "timeout"]

DEFAULT_INBOX_TIMEOUT_SEC = int(os.getenv("AGENT_LAB_INBOX_TIMEOUT_SEC", "1800"))
INBOX_POLL_SEC = float(os.getenv("AGENT_LAB_INBOX_POLL_SEC", "0.25"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "inbox") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def inbox_items(run: dict[str, Any]) -> list[dict[str, Any]]:
    raw = run.get("human_inbox")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def compute_inbox_pending(run: dict[str, Any]) -> bool:
    return any(item.get("status") == "pending" for item in inbox_items(run))


def pending_inbox_items(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in inbox_items(run) if item.get("status") == "pending"]


def find_inbox_item(run: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for item in inbox_items(run):
        if item.get("id") == item_id:
            return item
    return None


def has_pending_question(run: dict[str, Any]) -> bool:
    return any(
        item.get("status") == "pending" and item.get("kind") == "question"
        for item in inbox_items(run)
    )


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
        "pending_questions": sum(
            1 for item in pending if item.get("kind") == "question"
        ),
        "pending_builds": sum(1 for item in pending if item.get("kind") == "build"),
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
    )
    patch_run_meta(folder, lambda run: append_inbox_item(run, item))
    return item


def supersede_pending_inbox(folder: Path, *, human_turn_id: int | None = None) -> int:
    ts = _now_iso()
    count = 0

    def _supersede(run: dict[str, Any]) -> dict[str, Any]:
        nonlocal count
        for item in inbox_items(run):
            if item.get("status") != "pending":
                continue
            item["status"] = "superseded"
            item["superseded_at"] = ts
            if human_turn_id is not None:
                item["superseded_human_turn_id"] = human_turn_id
            count += 1
        run["human_inbox"] = inbox_items(run)
        return _sync_inbox_flag(run)

    patch_run_meta(folder, _supersede)
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
        return _sync_inbox_flag(run)

    patch_run_meta(folder, _resolve)
    if updated is None:
        raise ValueError(f"inbox item not found: {item_id}")

    if append_chat and status in ("resolved", "deferred"):
        _append_decision_to_chat(folder, updated)

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
        selected = [
            part.strip()
            for part in str(item["resolved_choice"]).split(",")
            if part.strip()
        ]
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
        run = read_run_meta(folder)
        item = find_inbox_item(run, item_id)
        if item is None:
            raise ValueError(f"inbox item not found: {item_id}")
        status = item.get("status")
        if status != "pending":
            return tool_result_for_item(item)
        time.sleep(interval)

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
) -> dict[str, Any]:
    if len(options) < 2:
        raise ValueError("ask_human requires at least 2 options")
    item = create_inbox_item(
        folder,
        kind="question",
        source="mcp_ask_human",
        prompt=question,
        options=options,
        multi_select=multi_select,
        context_ref=context_ref,
        mcp_call_id=mcp_call_id,
    )
    return wait_for_inbox_item(folder, item["id"])


def create_mcp_build_and_wait(
    folder: Path,
    *,
    summary: str,
    action_ref: str,
    risks: list[str] | None = None,
    mcp_call_id: str | None = None,
) -> dict[str, Any]:
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
