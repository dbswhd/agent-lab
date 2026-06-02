"""Advance plan.md after a saved thin execute (remove done item, promote next)."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from agent_lab.plan_actions import (
    NEXT_ACTIONS_HEADER,
    NOW_HEADER,
    ROADMAP_HEADER,
    ITEM_START,
    PlanAction,
    PlanActionKind,
    _parse_section_items,
    _section_body,
    action_key,
)

_EXECUTE_HEADERS = (NOW_HEADER, ROADMAP_HEADER, NEXT_ACTIONS_HEADER)


def _prefix_before_execute_sections(plan_md: str) -> str:
    earliest: int | None = None
    for header in _EXECUTE_HEADERS:
        match = header.search(plan_md or "")
        if match and (earliest is None or match.start() < earliest):
            earliest = match.start()
    if earliest is None:
        return (plan_md or "").rstrip()
    return plan_md[:earliest].rstrip()


def _render_item_at_index(item: PlanAction, new_index: int) -> str:
    lines = item.raw.splitlines()
    if not lines:
        return f"{new_index}."
    first = ITEM_START.match(lines[0].strip())
    if first:
        lines[0] = f"{new_index}. {first.group(2).strip()}"
    elif item.executable:
        lines.insert(0, f"{new_index}.")
    else:
        lines[0] = f"{new_index}. {item.summary}"
    return "\n".join(lines).strip()


def _render_section(items: list[PlanAction]) -> str:
    blocks = [_render_item_at_index(item, idx) for idx, item in enumerate(items, start=1)]
    return "\n\n".join(blocks)


def _remove_item(
    items: list[PlanAction],
    *,
    kind: PlanActionKind,
    index: int,
) -> list[PlanAction]:
    return [item for item in items if not (item.kind == kind and item.index == index)]


def _promote_first_executable_roadmap(
    now_items: list[PlanAction],
    roadmap_items: list[PlanAction],
) -> tuple[list[PlanAction], list[PlanAction], PlanAction | None]:
    if any(item.executable for item in now_items):
        return now_items, roadmap_items, None
    for idx, item in enumerate(roadmap_items):
        if not item.executable:
            continue
        promoted = replace(item, kind="now", recommended=True, index=1)
        now_items = [promoted]
        roadmap_items = roadmap_items[:idx] + roadmap_items[idx + 1 :]
        return now_items, roadmap_items, promoted
    return now_items, roadmap_items, None


def _compose_v1_plan(prefix: str, now_items: list[PlanAction], roadmap_items: list[PlanAction]) -> str:
    parts: list[str] = []
    if prefix:
        parts.append(prefix)
    if now_items:
        parts.append("## 지금 실행\n" + _render_section(now_items))
    if roadmap_items:
        parts.append("## 실행 순서 (이후)\n" + _render_section(roadmap_items))
    if not parts:
        return ""
    return "\n\n".join(parts).rstrip() + "\n"


def _compose_legacy_plan(prefix: str, legacy_items: list[PlanAction]) -> str:
    parts: list[str] = []
    if prefix:
        parts.append(prefix)
    if legacy_items:
        parts.append("## 다음에 할 일\n" + _render_section(legacy_items))
    if not parts:
        return ""
    return "\n\n".join(parts).rstrip() + "\n"


def advance_plan_md(
    plan_md: str,
    *,
    kind: PlanActionKind,
    index: int,
) -> tuple[str, dict[str, Any]]:
    """Remove completed action; promote next roadmap executable to 지금 실행 when needed."""
    meta: dict[str, Any] = {
        "removed_action_key": action_key(kind, index),
        "promoted_action_key": None,
        "changed": False,
    }
    if not plan_md.strip():
        return plan_md, meta

    prefix = _prefix_before_execute_sections(plan_md)
    now_body = _section_body(plan_md, NOW_HEADER)
    roadmap_body = _section_body(plan_md, ROADMAP_HEADER)
    legacy_body = _section_body(plan_md, NEXT_ACTIONS_HEADER)

    if now_body or roadmap_body:
        now_items = _parse_section_items(now_body, kind="now") if now_body else []
        roadmap_items = (
            _parse_section_items(roadmap_body, kind="roadmap") if roadmap_body else []
        )
        now_items = _remove_item(now_items, kind=kind, index=index)
        roadmap_items = _remove_item(roadmap_items, kind=kind, index=index)
        now_items, roadmap_items, promoted = _promote_first_executable_roadmap(
            now_items, roadmap_items
        )
        if promoted is not None:
            meta["promoted_action_key"] = action_key("now", 1)
        new_plan = _compose_v1_plan(prefix, now_items, roadmap_items)
    elif legacy_body:
        legacy_items = _parse_section_items(legacy_body, kind="legacy")
        legacy_items = _remove_item(legacy_items, kind=kind, index=index)
        new_plan = _compose_legacy_plan(prefix, legacy_items)
    else:
        return plan_md, meta

    normalized_new = new_plan.rstrip() + "\n" if new_plan else ""
    normalized_old = plan_md.rstrip() + "\n"
    meta["changed"] = normalized_new != normalized_old
    return normalized_new if meta["changed"] else plan_md, meta


def advance_plan_after_approval(folder: Path, execution: dict[str, Any]) -> dict[str, Any]:
    """Update plan.md after Human approves a pending execution."""
    status = str(execution.get("status") or "")
    if status not in {"completed", "review_required"}:
        return {"advanced": False, "reason": "not_saved"}

    kind_raw = execution.get("action_kind") or "now"
    if kind_raw not in ("now", "roadmap", "legacy"):
        kind_raw = "now"
    kind: PlanActionKind = kind_raw  # type: ignore[assignment]
    index = execution.get("action_index")
    if not isinstance(index, int) or index < 1:
        return {"advanced": False, "reason": "missing_action_index"}

    plan_path = folder / "plan.md"
    if not plan_path.is_file():
        return {"advanced": False, "reason": "plan_missing"}

    plan_md = plan_path.read_text(encoding="utf-8")
    new_plan, meta = advance_plan_md(plan_md, kind=kind, index=index)
    if not meta.get("changed"):
        return {"advanced": False, "reason": "unchanged", **meta}

    plan_path.write_text(new_plan, encoding="utf-8")
    return {"advanced": True, **meta}
