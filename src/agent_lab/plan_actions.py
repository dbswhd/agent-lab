"""Parse 3-field actionable items from plan.md."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from agent_lab.plan_execute_paths import filter_file_paths

PlanActionKind = Literal["now", "roadmap", "legacy"]


def action_key(kind: PlanActionKind, index: int) -> str:
    return f"{kind}:{index}"


def parse_action_key(raw: str) -> tuple[PlanActionKind, int] | None:
    text = (raw or "").strip()
    if ":" not in text:
        return None
    kind_str, index_str = text.split(":", 1)
    if kind_str not in ("now", "roadmap", "legacy"):
        return None
    try:
        index = int(index_str)
    except ValueError:
        return None
    if index < 1:
        return None
    return kind_str, index  # type: ignore[return-value]


NEXT_ACTIONS_HEADER = re.compile(r"^##\s+다음에\s+할\s+일\s*$", re.MULTILINE)
NOW_HEADER = re.compile(r"^##\s+지금\s+실행\s*$", re.MULTILINE)
ROADMAP_HEADER = re.compile(r"^##\s+실행\s+순서(?:\s*\(이후\))?\s*$", re.MULTILINE)
ITEM_START = re.compile(r"(?m)^(\d+)\.\s*(.*)$")
FIELD_WHAT = re.compile(r"^\s*-\s*무엇을:\s*(.+?)\s*$")
FIELD_WHERE = re.compile(r"^\s*-\s*어디서:\s*(.+?)\s*$")
FIELD_VERIFY = re.compile(r"^\s*-\s*검증:\s*(.+?)\s*$")
FIELD_ISOLATION = re.compile(r"^\s*-\s*isolation:\s*(auto|worktree|apply|block)\s*$", re.I)
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
    isolation: str = "auto"

    def to_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "index": self.index,
            "what": self.what,
            "where": self.where,
            "verify": self.verify,
            "refs": list(self.refs),
            "expected_paths": self.expected_paths(),
            "verification_paths": self.verification_paths(),
            "monitored_paths": self.monitored_paths(),
            "action_key": action_key(self.kind, self.index),
            "raw": self.raw,
            "recommended": self.recommended,
            "kind": self.kind,
            "executable": self.executable,
            "isolation": self.isolation,
        }
        if not self.executable and self.summary:
            row["summary"] = self.summary
        return row

    def expected_paths(self) -> list[str]:
        if not self.executable:
            return []
        tokens = [match.group(1).strip() for match in PATH_IN_BACKTICKS.finditer(self.where)]
        return filter_file_paths(tokens)

    def verification_paths(self) -> list[str]:
        if not self.executable:
            return []
        tokens = [match.group(1).strip() for match in PATH_IN_BACKTICKS.finditer(self.verify)]
        return filter_file_paths(tokens)

    def monitored_paths(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for path in self.expected_paths() + self.verification_paths():
            if path in seen:
                continue
            seen.add(path)
            out.append(path)
        return out

    @property
    def action_id(self) -> str:
        return f"plan-action-{self.kind}-{self.index}"


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
    isolation = "auto"
    for line in block.splitlines():
        if m := FIELD_WHAT.match(line):
            what = m.group(1).strip()
        elif m := FIELD_WHERE.match(line):
            where = m.group(1).strip()
        elif m := FIELD_VERIFY.match(line):
            verify = m.group(1).strip()
        elif m := FIELD_ISOLATION.match(line):
            isolation = m.group(1).strip().lower()

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
            isolation=isolation,
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
        isolation=isolation,
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
    now_rows = [item.to_dict() for item in (now_items if now_body else [])]
    return {
        "recommended": recommended.to_dict() if recommended else None,
        "now": now_rows,
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
        "isolation": row.get("isolation") or "auto",
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


def find_dry_run_action(
    plan_md: str,
    index: int,
    *,
    kind: PlanActionKind | None = None,
) -> PlanAction | None:
    """Resolve an action for dry-run by section kind + index."""
    sections = parse_plan_action_sections(plan_md)
    recommended = sections.get("recommended")

    if kind in (None, "now") and recommended and recommended.get("index") == index:
        return PlanAction(**_action_from_dict(recommended))

    if kind in (None, "roadmap"):
        for row in sections.get("roadmap") or []:
            if row.get("index") != index or not row.get("executable"):
                continue
            if kind == "roadmap" or row.get("kind") == "roadmap":
                return PlanAction(**_action_from_dict(row))

    if kind == "legacy":
        for row in sections.get("actions") or []:
            if row.get("index") == index and row.get("executable"):
                return PlanAction(**_action_from_dict(row))

    return None


def validate_plan_actions_format(plan_md: str) -> dict[str, Any]:
    """Check plan.md execute sections after scribe; non-fatal warnings for room SSE."""
    text = plan_md or ""
    sections = parse_plan_action_sections(text)
    has_now = bool(NOW_HEADER.search(text))
    has_roadmap = bool(ROADMAP_HEADER.search(text))
    has_legacy = bool(NEXT_ACTIONS_HEADER.search(text))
    recommended = sections.get("recommended")
    executable_count = len(sections.get("all_executable") or [])
    now_rows = sections.get("now") or []

    issues: list[str] = []
    if not has_now and not has_legacy:
        issues.append("missing_execute_section")
    elif has_now:
        if not now_rows:
            issues.append("empty_now_section")
        elif not recommended:
            issues.append("no_executable_now_action")
    elif has_legacy and not recommended:
        issues.append("no_executable_legacy_action")

    if has_now and not has_roadmap and executable_count > 1:
        issues.append("missing_roadmap_section")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "has_now_section": has_now,
        "has_roadmap_section": has_roadmap,
        "has_legacy_section": has_legacy,
        "executable_count": executable_count,
        "recommended_action_key": (recommended or {}).get("action_key"),
    }
