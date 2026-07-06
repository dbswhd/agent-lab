"""Session plan file paths — keep core plan.md separate from extension plans."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.run.state import RunState, RunStateLike

TRADING_MISSION_PLAN_REL = "artifacts/plans/trading-mission.md"
LEGACY_TRADING_SECTION_MARKERS = (
    "ingest_ready",
    "freshness.blocking",
    "proposal_delta.json",
    "kr_kospi_v1",
    "Trading Mission",
)

_PLAN_PATH_RE = re.compile(
    r"^\s*<!--\s*plan-path:\s*([^\s>]+\.md)\s*-->\s*$",
    re.I,
)


def session_plan_path(folder: Path) -> Path:
    return folder / "plan.md"


def session_plans_dir(folder: Path) -> Path:
    return folder / "artifacts" / "plans"


def fresh_plan_md_stub() -> str:
    return "# Plan\n\n"


def _plan_stub_content(content: str) -> bool:
    return content.strip() in {"", fresh_plan_md_stub().strip(), "# Plan"}


def normalize_plan_relpath(raw: str) -> str:
    rel = raw.strip().lstrip("/")
    if not rel.lower().endswith(".md"):
        rel = f"{rel}.md"
    name = Path(rel).name
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in name)
    safe = safe.strip("-") or "plan.md"
    return f"artifacts/plans/{safe}"


def extract_plan_path_directive(plan_md: str) -> tuple[str | None, str]:
    lines = plan_md.splitlines()
    for idx, line in enumerate(lines[:8]):
        match = _PLAN_PATH_RE.match(line)
        if not match:
            continue
        rel = normalize_plan_relpath(match.group(1))
        body = "\n".join(lines[:idx] + lines[idx + 1 :]).lstrip("\n")
        return rel, body
    return None, plan_md


def slug_from_plan_h1(plan_md: str) -> str:
    for line in plan_md.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()[:80]
            slug = "".join(ch if ch.isalnum() else "-" for ch in title.lower())
            parts = [part for part in slug.split("-") if part]
            return "-".join(parts)[:60] or "plan"
    return "plan"


def resolve_new_plan_relpath(plan_md: str, run_meta: RunStateLike) -> str:
    directive, _ = extract_plan_path_directive(plan_md)
    if directive:
        return directive
    seq = len(run_meta.get("plan_cycles") or []) + 1
    slug = slug_from_plan_h1(plan_md)
    return f"artifacts/plans/{seq:03d}-{slug}.md"


def active_plan_relpath(run_meta: RunStateLike | None) -> str:
    if not isinstance(run_meta, dict):
        return "plan.md"
    rel = str(run_meta.get("active_plan_relpath") or "").strip()
    return rel or "plan.md"


def read_session_plan_md(folder: Path, run_meta: RunStateLike | None = None) -> str:
    from agent_lab.run.meta import read_run_meta

    meta = run_meta if run_meta is not None else read_run_meta(folder)
    rel = active_plan_relpath(meta)
    path = folder / rel
    if path.is_file():
        return path.read_text(encoding="utf-8")
    legacy = session_plan_path(folder)
    if legacy.is_file():
        return legacy.read_text(encoding="utf-8")
    return ""


def write_session_plan_md(
    folder: Path,
    plan_md: str,
    run_meta: RunStateLike,
) -> tuple[Path, str]:
    """Write plan to artifacts/plans/{agent-chosen}.md; mirror plan.md for legacy readers."""
    _, body = extract_plan_path_directive(plan_md)
    if not str(run_meta.get("active_plan_relpath") or "").strip():
        from agent_lab.run.meta import stamp_run_meta

        stamp_run_meta(
            run_meta,
            active_plan_relpath=resolve_new_plan_relpath(plan_md, run_meta),
        )
    rel = active_plan_relpath(run_meta)
    path = folder / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = (body or plan_md).rstrip() + "\n"
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if existing == normalized:
            return path, rel
    path.write_text(normalized, encoding="utf-8")
    session_plan_path(folder).write_text(normalized, encoding="utf-8")
    return path, rel


def _archive_plan_content(
    folder: Path,
    run_meta: RunStateLike,
    *,
    source_rel: str,
    content: str,
) -> str:
    cycles: list[dict[str, Any]] = list(run_meta.get("plan_cycles") or [])
    seq = len(cycles) + 1
    if source_rel.startswith("artifacts/plans/"):
        rel = source_rel
    else:
        name = Path(source_rel).name
        if name == "plan.md":
            rel = f"artifacts/plans/plan-{seq:03d}.md"
        else:
            rel = f"artifacts/plans/{seq:03d}-{name}"
    dest = folder / rel
    if not dest.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content.rstrip() + "\n", encoding="utf-8")
    cycles.append(
        {
            "seq": seq,
            "relpath": rel,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "source": source_rel,
        }
    )
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(run_meta, plan_cycles=cycles, plan_cycle_seq=seq + 1)
    return rel


def begin_session_plan_cycle(folder: Path, run_meta: RunStateLike) -> str | None:
    """Archive the active plan and clear path for the next scribe write."""
    rel = str(run_meta.get("active_plan_relpath") or "plan.md")
    path = folder / rel
    if not path.is_file():
        path = session_plan_path(folder)
        rel = "plan.md"
    archived: str | None = None
    if path.is_file():
        content = path.read_text(encoding="utf-8")
        if not _plan_stub_content(content):
            archived = _archive_plan_content(
                folder,
                run_meta,
                source_rel=rel,
                content=content,
            )
    run_meta.pop("active_plan_relpath", None)
    if path.is_file() and path.name == "plan.md":
        path.unlink(missing_ok=True)
    return archived


def extension_plan_path(folder: Path, domain: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in domain.strip().lower())
    safe = safe.strip("-") or "extension"
    return folder / "artifacts" / "plans" / f"{safe}.md"


def trading_mission_plan_path(folder: Path) -> Path:
    return folder / TRADING_MISSION_PLAN_REL


def is_trading_mission_run(run_meta: RunStateLike | None) -> bool:
    if not isinstance(run_meta, dict):
        return False
    template = str(run_meta.get("session_template") or "").strip().lower()
    if template in {"trading-mission", "trading-thin", "trading-offline"}:
        return True
    mission_kind = str(run_meta.get("mission_kind") or "").strip().lower()
    return mission_kind.startswith("trading")


def read_trading_plan_md(folder: Path) -> str:
    """Prefer extension plan; fall back to legacy plan.md trading sections."""
    ext = trading_mission_plan_path(folder)
    if ext.is_file():
        return ext.read_text(encoding="utf-8")
    legacy = session_plan_path(folder)
    if not legacy.is_file():
        return ""
    text = legacy.read_text(encoding="utf-8")
    if any(marker in text for marker in LEGACY_TRADING_SECTION_MARKERS):
        return text
    return ""


def write_trading_plan_md(folder: Path, content: str) -> Path:
    path = trading_mission_plan_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path
