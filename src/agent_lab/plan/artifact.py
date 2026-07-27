"""Typed plan artifact — the execution layer's input (P1).

Background
----------
``plan.md`` is LLM-authored prose and the executable action list was recovered from it
by regex (``plan/actions.py``) *lazily, at every read site*. When the regex matched
nothing the result was an empty list that flowed on silently: no error, no notice, and
an execute queue with nothing in it. Measured across 874 real session plans, 8.2%
parsed to zero executable actions — 44 of them because the scribe wrote a perfectly
human-readable plan that simply never used a recognised section header.

This module moves the parse from read-time to **write-time**: every plan write parses
once, validates, and persists a typed artifact with diagnostics. Downstream reads take
the typed artifact, so execution no longer depends on re-running a regex over prose,
and a plan that cannot drive execution says so at the moment it is written.

``plan.md`` remains the human view and stays authoritative for *content*; the artifact
is a derived index keyed by content hash, so a stale artifact is always detectable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agent_lab.plan.actions import (
    ITEM_START,
    NEXT_ACTIONS_HEADER,
    NOW_HEADER,
    ROADMAP_HEADER,
    PlanAction,
    parse_plan_actions,
)
from agent_lab.time_utils import utc_now_iso

PLAN_ARTIFACT_SCHEMA_VERSION: Final[int] = 1
PLAN_ARTIFACT_RELPATH: Final[str] = ".agent-lab/plan-actions.json"

#: Minimum body length below which a plan is treated as a stub rather than a real plan.
_STUB_CHARS: Final[int] = 40


@dataclass(frozen=True, slots=True)
class PlanDiagnostic:
    """Why a plan cannot drive execution, in terms the author can act on."""

    code: str
    message: str
    hint: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "hint": self.hint}


@dataclass(frozen=True, slots=True)
class PlanArtifact:
    schema_version: int
    plan_hash: str
    source_relpath: str
    generated_at: str
    actions: tuple[dict[str, Any], ...] = ()
    diagnostics: tuple[PlanDiagnostic, ...] = ()

    @property
    def executable_actions(self) -> tuple[dict[str, Any], ...]:
        return tuple(row for row in self.actions if row.get("executable"))

    @property
    def executable_count(self) -> int:
        return len(self.executable_actions)

    @property
    def is_executable(self) -> bool:
        return self.executable_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_hash": self.plan_hash,
            "source_relpath": self.source_relpath,
            "generated_at": self.generated_at,
            "executable_count": self.executable_count,
            "actions": [dict(row) for row in self.actions],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }

    @classmethod
    def from_dict(cls, raw: object) -> PlanArtifact | None:
        if not isinstance(raw, dict):
            return None
        if raw.get("schema_version") != PLAN_ARTIFACT_SCHEMA_VERSION:
            return None
        plan_hash = raw.get("plan_hash")
        if not isinstance(plan_hash, str) or not plan_hash:
            return None
        actions_raw = raw.get("actions")
        actions = tuple(row for row in actions_raw if isinstance(row, dict)) if isinstance(actions_raw, list) else ()
        diags_raw = raw.get("diagnostics")
        diagnostics: tuple[PlanDiagnostic, ...] = ()
        if isinstance(diags_raw, list):
            diagnostics = tuple(
                PlanDiagnostic(
                    str(d.get("code") or ""),
                    str(d.get("message") or ""),
                    str(d.get("hint") or ""),
                )
                for d in diags_raw
                if isinstance(d, dict)
            )
        return cls(
            schema_version=PLAN_ARTIFACT_SCHEMA_VERSION,
            plan_hash=plan_hash,
            source_relpath=str(raw.get("source_relpath") or ""),
            generated_at=str(raw.get("generated_at") or ""),
            actions=actions,
            diagnostics=diagnostics,
        )


def diagnose_plan(plan_md: str, actions: list[PlanAction] | None = None) -> tuple[PlanDiagnostic, ...]:
    """Explain why ``plan_md`` yields no executable action. Empty when it does."""
    text = plan_md or ""
    parsed = actions if actions is not None else list(parse_plan_actions(text))
    if any(a.executable for a in parsed):
        return ()

    body = text.strip()
    if len(body) < _STUB_CHARS:
        return (
            PlanDiagnostic(
                "empty_plan",
                "plan.md is empty or a stub, so there is nothing to execute.",
                "Write the plan before requesting execution.",
            ),
        )

    has_header = bool(NOW_HEADER.search(text) or ROADMAP_HEADER.search(text) or NEXT_ACTIONS_HEADER.search(text))
    if not has_header:
        return (
            PlanDiagnostic(
                "no_section_header",
                "plan.md has content but no executable section header, so no action was found.",
                "Add a '## 지금 실행' (or '## 실행 순서' / '## 다음에 할 일') section.",
            ),
        )

    if not ITEM_START.search(text):
        return (
            PlanDiagnostic(
                "no_numbered_items",
                "The executable section has no numbered items.",
                "List actions as '1.', '2.', … inside the section.",
            ),
        )

    return (
        PlanDiagnostic(
            "incomplete_action_fields",
            "Numbered items exist but none carry all three required fields.",
            "Each action needs '- 무엇을:', '- 어디서:' and '- 검증:'.",
        ),
    )


def build_plan_artifact(plan_md: str, *, source_relpath: str = "plan.md") -> PlanArtifact:
    """Parse ``plan_md`` once and produce the typed artifact (with diagnostics)."""
    from agent_lab.plan.pending import plan_content_hash

    parsed = list(parse_plan_actions(plan_md or ""))
    return PlanArtifact(
        schema_version=PLAN_ARTIFACT_SCHEMA_VERSION,
        plan_hash=plan_content_hash(plan_md or ""),
        source_relpath=source_relpath,
        generated_at=utc_now_iso(),
        actions=tuple(a.to_dict() for a in parsed),
        diagnostics=diagnose_plan(plan_md or "", parsed),
    )


def plan_artifact_path(folder: Path) -> Path:
    return folder / PLAN_ARTIFACT_RELPATH


def write_plan_artifact(folder: Path, artifact: PlanArtifact) -> Path:
    path = plan_artifact_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(artifact.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def read_plan_artifact(folder: Path) -> PlanArtifact | None:
    path = plan_artifact_path(folder)
    if not path.is_file():
        return None
    try:
        return PlanArtifact.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def refresh_plan_artifact(folder: Path, plan_md: str, *, source_relpath: str = "plan.md") -> PlanArtifact:
    """Rebuild and persist the artifact for ``plan_md`` (called from the plan write seam)."""
    artifact = build_plan_artifact(plan_md, source_relpath=source_relpath)
    try:
        write_plan_artifact(folder, artifact)
    except OSError:
        # A read-only or missing session folder must not break plan writing; the
        # typed-first readers fall back to parsing plan.md.
        pass
    return artifact


def plan_artifact_for(folder: Path, plan_md: str, *, source_relpath: str = "plan.md") -> PlanArtifact:
    """Typed artifact for the current plan, rebuilding transparently when stale.

    Backward compatible: sessions written before this artifact existed simply get one
    built on demand, so no migration is required.
    """
    from agent_lab.plan.pending import plan_content_hash

    stored = read_plan_artifact(folder)
    if stored is not None and stored.plan_hash == plan_content_hash(plan_md or ""):
        return stored
    return build_plan_artifact(plan_md, source_relpath=source_relpath)


def plan_execution_blocker(folder: Path, plan_md: str) -> str | None:
    """Human-facing reason the current plan cannot drive execution, or ``None``.

    This is the loud surface the silent empty-list path never had.
    """
    artifact = plan_artifact_for(folder, plan_md)
    if artifact.is_executable:
        return None
    if not artifact.diagnostics:
        return "plan.md has no executable action."
    first = artifact.diagnostics[0]
    return f"{first.message} {first.hint}".strip()


def scribe_repair_instruction(artifact: PlanArtifact) -> str:
    """Corrective instruction fed back to the scribe when its plan cannot execute.

    Returns "" when the plan is fine, so callers can treat truthiness as "needs repair".
    """
    if artifact.is_executable or not artifact.diagnostics:
        return ""
    lines = [
        "The plan you just wrote cannot drive execution — it produced no executable action.",
        "",
        "Problem:",
    ]
    for diagnostic in artifact.diagnostics:
        lines.append(f"- {diagnostic.message}")
        if diagnostic.hint:
            lines.append(f"  Fix: {diagnostic.hint}")
    lines += [
        "",
        "Rewrite the plan so it contains at least one executable action under",
        "'## 지금 실행', each numbered item carrying all three fields:",
        "  - 무엇을: <what to change>",
        "  - 어디서: <`path/to/file`>",
        "  - 검증: <command or check that proves it>",
        "",
        "Keep the rest of the plan's content and intent; only make it executable.",
    ]
    return "\n".join(lines)


def _diagnostics_payload(artifact: PlanArtifact) -> list[dict[str, str]]:
    return [d.to_dict() for d in artifact.diagnostics]


def plan_artifact_public(artifact: PlanArtifact) -> dict[str, Any]:
    """Read-model payload for API/UI consumers."""
    return {
        "plan_hash": artifact.plan_hash,
        "executable_count": artifact.executable_count,
        "is_executable": artifact.is_executable,
        "diagnostics": _diagnostics_payload(artifact),
        "generated_at": artifact.generated_at,
    }


__all__ = [
    "PLAN_ARTIFACT_RELPATH",
    "PLAN_ARTIFACT_SCHEMA_VERSION",
    "PlanArtifact",
    "PlanDiagnostic",
    "build_plan_artifact",
    "diagnose_plan",
    "plan_artifact_for",
    "plan_artifact_path",
    "plan_artifact_public",
    "plan_execution_blocker",
    "read_plan_artifact",
    "refresh_plan_artifact",
    "scribe_repair_instruction",
    "write_plan_artifact",
]
