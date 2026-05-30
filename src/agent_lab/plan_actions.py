"""Parse 3-field actionable items from plan.md."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Literal

PlanActionKind = Literal["now", "roadmap", "legacy"]

NEXT_ACTIONS_HEADER = re.compile(r"^##\s+다음에\s+할\s+일\s*$", re.MULTILINE)
NOW_HEADER = re.compile(r"^##\s+지금\s+실행\s*$", re.MULTILINE)
ROADMAP_HEADER = re.compile(r"^##\s+실행\s+순서(?:\s*\(이후\))?\s*$", re.MULTILINE)
ITEM_START = re.compile(r"(?m)^(\d+)\.\s*(.*)$")
FIELD_WHAT = re.compile(r"^\s*-\s*무엇을:\s*(.+?)\s*$")
FIELD_WHERE = re.compile(r"^\s*-\s*어디서:\s*(.+?)\s*$")
FIELD_VERIFY = re.compile(r"^\s*-\s*검증:\s*(.+?)\s*$")
REF_PATTERN = re.compile(r"\(ref:\s*([^)]+)\)")
PATH_IN_BACKTICKS = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class PlanAction:
    index: int
    what: str
    where: str
    verify: str
    refs: tuple[str, ...]
    raw: str
    recommended: bool = False
    kind: PlanActionKind = "legacy"
    executable: bool = True
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "index": self.index,
            "what": self.what,
            "where": self.where,
            "verify": self.verify,
            "refs": list(self.refs),
            "expected_paths": self.expected_paths(),
            "raw": self.raw,
            "recommended": self.recommended,
            "kind": self.kind,
            "executable": self.executable,
        }
        if not self.executable and self.summary:
            row["summary"] = self.summary
        return row

    def expected_paths(self) -> list[str]:
        if not self.executable:
            return []
        paths: list[str] = []
        for match in PATH_IN_BACKTICKS.finditer(self.where):
            path = match.group(1).strip()
            if not path or path in paths:
                continue
            if "/" in path or re.search(r"\.\w+$", path):
                paths.append(path)
        return paths

    @property
    def action_id(self) -> str:
        return f"plan-action-{self.index}"


def _section_body(plan_md: str, header: re.Pattern[str]) -> str:
    text = plan_md or ""
    match = header.search(text)
    if not match:
        return ""
    rest = text[match.end() :]
    next_header = re.search(r"(?m)^##\s+", rest)
    if next_header:
        rest = rest[: next_header.start()]
    return rest.strip()


def _refs_from_text(text: str) -> tuple[str, ...]:
    refs: list[str] = []
    for match in REF_PATTERN.finditer(text):
        chunk = match.group(1).strip()
        for part in chunk.split(","):
            ref = part.strip()
            if ref and ref not in refs:
                refs.append(ref)
    return tuple(refs)


def _parse_item_block(
    block: str,
    *,
    index: int,
    kind: PlanActionKind,
    recommended: bool = False,
) -> PlanAction | None:
    what = where = verify = ""
    for line in block.splitlines():
        if m := FIELD_WHAT.match(line):
            what = m.group(1).strip()
        elif m := FIELD_WHERE.match(line):
            where = m.group(1).strip()
        elif m := FIELD_VERIFY.match(line):
            verify = m.group(1).strip()

    if what and where and verify:
        return PlanAction(
            index=index,
            what=what,
            where=where,
            verify=verify,
            refs=_refs_from_text(block),
            raw=block,
            recommended=recommended,
            kind=kind,
            executable=True,
        )

    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        return None
    first = ITEM_START.match(lines[0])
    summary = first.group(2).strip() if first else lines[0]
    if not summary:
        return None
    return PlanAction(
        index=index,
        what=summary,
        where="",
        verify="",
        refs=_refs_from_text(block),
        raw=block,
        recommended=recommended,
        kind=kind,
        executable=False,
        summary=summary,
    )


def _parse_section_items(
    body: str,
    *,
    kind: PlanActionKind,
    recommended_index: int | None = None,
) -> list[PlanAction]:
    if not body:
        return []

    matches = list(ITEM_START.finditer(body))
    if not matches:
        return []

    items: list[PlanAction] = []
    for i, match in enumerate(matches):
        index = int(match.group(1))
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block = body[start:end].strip()
        item = _parse_item_block(
            block,
            index=index,
            kind=kind,
            recommended=(recommended_index == index),
        )
        if item is not None:
            items.append(item)
    return items


def parse_plan_action_sections(plan_md: str) -> dict[str, Any]:
    """Return recommended action, roadmap steps, and all executable actions."""
    now_body = _section_body(plan_md, NOW_HEADER)
    roadmap_body = _section_body(plan_md, ROADMAP_HEADER)
    legacy_body = _section_body(plan_md, NEXT_ACTIONS_HEADER)

    recommended: PlanAction | None = None
    roadmap: list[PlanAction] = []
    all_executable: list[PlanAction] = []

    if now_body:
        now_items = _parse_section_items(now_body, kind="now")
        executable_now = [item for item in now_items if item.executable]
        if executable_now:
            recommended = replace(executable_now[0], recommended=True)
            all_executable.append(recommended)
        if roadmap_body:
            roadmap = _parse_section_items(roadmap_body, kind="roadmap")
            for item in roadmap:
                if item.executable:
                    all_executable.append(item)
    elif legacy_body:
        legacy_items = _parse_section_items(legacy_body, kind="legacy")
        saw_recommended = False
        for item in legacy_items:
            if item.executable and not saw_recommended:
                recommended = replace(item, recommended=True)
                all_executable.append(recommended)
                saw_recommended = True
            else:
                roadmap.append(item)
                if item.executable:
                    all_executable.append(item)

    executable_rows = [action.to_dict() for action in all_executable]
    return {
        "recommended": recommended.to_dict() if recommended else None,
        "roadmap": [item.to_dict() for item in roadmap],
        "all_executable": executable_rows,
        "actions": executable_rows,
    }


def parse_plan_actions(plan_md: str) -> list[PlanAction]:
    sections = parse_plan_action_sections(plan_md)
    return [PlanAction(**_action_from_dict(row)) for row in sections["all_executable"]]


def _action_from_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": row["index"],
        "what": row["what"],
        "where": row["where"],
        "verify": row["verify"],
        "refs": tuple(row.get("refs") or []),
        "raw": row.get("raw") or "",
        "recommended": bool(row.get("recommended")),
        "kind": row.get("kind") or "legacy",
        "executable": bool(row.get("executable", True)),
        "summary": row.get("summary") or "",
    }


def find_plan_action(plan_md: str, index: int) -> PlanAction | None:
    sections = parse_plan_action_sections(plan_md)
    recommended = sections.get("recommended")
    if recommended and recommended.get("index") == index:
        return PlanAction(**_action_from_dict(recommended))
    for row in sections.get("roadmap") or []:
        if row.get("index") == index and row.get("executable"):
            return PlanAction(**_action_from_dict(row))
    for row in sections.get("actions") or []:
        if row.get("index") == index:
            return PlanAction(**_action_from_dict(row))
    return None


def find_dry_run_action(plan_md: str, index: int) -> PlanAction | None:
    """Resolve an action for dry-run: recommended first, then roadmap 3-field."""
    sections = parse_plan_action_sections(plan_md)
    recommended = sections.get("recommended")
    if recommended and recommended.get("index") == index:
        return PlanAction(**_action_from_dict(recommended))
    for row in sections.get("roadmap") or []:
        if row.get("index") == index and row.get("executable"):
            return PlanAction(**_action_from_dict(row))
    return None
