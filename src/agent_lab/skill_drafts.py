"""Skill drafts — verify PASS → session skill + Human promote to workspace."""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_lab.gate_scope import get_gate_profile
from agent_lab.run_meta import patch_run_meta, read_run_meta

DraftStatus = Literal["pending_promote", "promoted", "rejected", "session_only"]


def skill_drafts_enabled() -> bool:
    return os.getenv("AGENT_LAB_SKILL_DRAFTS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_draft_id() -> str:
    return f"skdraft-{uuid.uuid4().hex[:12]}"


def session_skills_root(folder: Path) -> Path:
    return folder / "skills"


def session_drafts_root(folder: Path) -> Path:
    return session_skills_root(folder) / "_drafts"


def workspace_skills_root() -> Path:
    from agent_lab.workspace_roots import user_agent_lab_root

    return user_agent_lab_root() / ".agent-lab" / "skills"


def _slugify(text: str, *, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "lesson")[:max_len].strip("-")


def slug_for_execution(execution: dict[str, Any]) -> str:
    idx = execution.get("action_index")
    summary = str(
        execution.get("draft_summary") or execution.get("action_verify") or execution.get("action_id") or "lesson"
    )
    base = _slugify(summary)
    if idx is not None:
        return _slugify(f"verify-{idx}-{base}", max_len=56)
    return _slugify(f"verify-{base}", max_len=56)


def skill_draft_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    raw = run.get("skill_drafts")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def find_skill_draft(run: dict[str, Any], draft_id: str) -> dict[str, Any] | None:
    for row in skill_draft_rows(run):
        if str(row.get("id") or "") == draft_id:
            return row
    return None


def _draft_for_execution(run: dict[str, Any], execution_id: str) -> dict[str, Any] | None:
    for row in skill_draft_rows(run):
        if str(row.get("execution_id") or "") == execution_id:
            return row
    return None


def verify_evidence_passed(evidence: dict[str, Any]) -> bool:
    oracle = evidence.get("oracle") if isinstance(evidence.get("oracle"), dict) else {}
    verdict = str(oracle.get("verdict") or evidence.get("status") or "").lower()
    if verdict in {"pass", "passed"}:
        return True
    return str(evidence.get("status") or "").lower() == "passed"


def session_auto_allowed(run: dict[str, Any], execution: dict[str, Any]) -> bool:
    """Phase B — assistant always; dev only for read-only classifier kinds."""
    if get_gate_profile(run) == "assistant":
        return True
    from agent_lab.merge_classifier import classify_execution

    kind = classify_execution(execution)
    return kind in ("docs_only", "test_only")


def render_skill_markdown(
    *,
    slug: str,
    execution: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    exec_id = str(execution.get("id") or "")
    verify_line = str(execution.get("action_verify") or "").strip()
    summary = str(execution.get("draft_summary") or "").strip()
    paths = list(execution.get("source_touched_paths") or execution.get("touched_paths") or [])
    oracle = evidence.get("oracle") if isinstance(evidence.get("oracle"), dict) else {}
    oracle_detail = str(oracle.get("detail") or oracle.get("feedback") or oracle.get("reason") or "").strip()
    desc = summary or verify_line or f"Verified lesson from {exec_id}"
    if len(desc) > 160:
        desc = desc[:157] + "..."

    lines = [
        "---",
        f"name: {slug}",
        f"description: {desc}",
        "tools: Read, Bash",
        "---",
        "",
        f"# {slug.replace('-', ' ').title()}",
        "",
        "## Verify criterion",
        verify_line or "(none recorded)",
        "",
    ]
    if summary:
        lines.extend(["## Summary", summary, ""])
    if paths:
        lines.extend(["## Paths touched", *[f"- `{p}`" for p in paths], ""])
    if oracle_detail:
        lines.extend(["## Oracle feedback", oracle_detail, ""])
    lines.extend(
        [
            "## Usage",
            "Apply this lesson when a similar verify criterion or path pattern appears.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _register_session_skill(folder: Path, slug: str, content: str) -> Path:
    dest = session_skills_root(folder) / slug / "SKILL.md"
    _write_text(dest, content)
    return dest


def _append_draft_row(run: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    rows = skill_draft_rows(run)
    rows.append(row)
    run["skill_drafts"] = rows
    skills = list(run.get("session_skills") or [])
    slug = str(row.get("slug") or "")
    if slug and slug not in skills:
        skills.append(slug)
    run["session_skills"] = skills
    return run


def maybe_create_skill_draft_from_verify(
    folder: Path,
    execution: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any] | None:
    """Hook from plan_execute verify PASS — draft file, optional session skill, inbox."""
    if not skill_drafts_enabled():
        return None
    if not verify_evidence_passed(evidence):
        return None
    exec_id = str(execution.get("id") or "")
    if not exec_id:
        return None

    run = read_run_meta(folder)
    if _draft_for_execution(run, exec_id) is not None:
        return _draft_for_execution(run, exec_id)

    slug = slug_for_execution(execution)
    draft_id = _new_draft_id()
    content = render_skill_markdown(slug=slug, execution=execution, evidence=evidence)
    draft_rel = f"skills/_drafts/{slug}.md"
    draft_path = folder / draft_rel
    _write_text(draft_path, content)

    session_rel: str | None = None
    status: DraftStatus = "pending_promote"
    if session_auto_allowed(run, execution):
        session_path = _register_session_skill(folder, slug, content)
        session_rel = str(session_path.relative_to(folder))
        status = "session_only"

    inbox_item: dict[str, Any] | None = None
    from agent_lab.human_inbox import create_inbox_item

    prompt = f"Promote verified skill `{slug}` to workspace `.agent-lab/skills/`?"
    inbox_item = create_inbox_item(
        folder,
        kind="skill_draft",
        source="verify_pass",
        prompt=prompt,
        summary=str(execution.get("draft_summary") or execution.get("action_verify") or slug),
        options=[
            {"id": "approve", "label": "Promote to workspace skills"},
            {"id": "reject", "label": "Reject promote"},
        ],
        refs=[draft_id, slug, exec_id],
        context_ref=draft_rel,
    )

    row = {
        "id": draft_id,
        "slug": slug,
        "execution_id": exec_id,
        "status": status,
        "draft_path": draft_rel,
        "session_skill_path": session_rel,
        "inbox_id": inbox_item.get("id"),
        "created_at": _now_iso(),
        "promoted_at": None,
        "promoted_path": None,
    }

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        return _append_draft_row(run, row)

    patch_run_meta(folder, _patch)
    return row


def public_skill_drafts_payload(folder: Path) -> dict[str, Any]:
    run = read_run_meta(folder)
    rows = skill_draft_rows(run)
    pending = [r for r in rows if str(r.get("status") or "") in {"pending_promote", "session_only"}]
    return {
        "skill_drafts": rows,
        "session_skills": list(run.get("session_skills") or []),
        "pending_promote_count": len(pending),
        "enabled": skill_drafts_enabled(),
    }


def list_session_skill_files(folder: Path) -> list[Path]:
    root = session_skills_root(folder)
    if not root.is_dir():
        return []
    return sorted(root.glob("*/SKILL.md"))


def build_session_skills_block(
    run_meta: dict[str, Any] | None,
    *,
    folder: Path | None = None,
    max_chars: int = 2400,
) -> str:
    if not skill_drafts_enabled() or not run_meta:
        return ""
    folder_raw = folder or run_meta.get("_session_folder")
    if not folder_raw:
        return ""
    session_folder = Path(str(folder_raw))
    if not session_folder.is_dir():
        return ""

    slugs = list(run_meta.get("session_skills") or [])
    paths = list_session_skill_files(session_folder)
    if not slugs and not paths:
        return ""

    lines = [
        "## Session skills (learned this mission)",
        "Use these before workspace `.claude/skills` when relevant.",
        "",
    ]
    used: set[str] = set()
    for path in paths:
        slug = path.parent.name
        if slug.startswith("_"):
            continue
        used.add(slug)
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        desc = slug.replace("-", " ")
        if body.startswith("---"):
            end = body.find("---", 3)
            if end != -1:
                front = body[3:end]
                for line in front.splitlines():
                    if line.strip().lower().startswith("description:"):
                        desc = line.split(":", 1)[1].strip().strip('"')
                        break
        lines.append(f"- **{slug}**: {desc}")
        excerpt = body.strip()
        if len(excerpt) > 400:
            excerpt = excerpt[:397] + "..."
        lines.append(f"  ```\n  {excerpt.replace(chr(10), chr(10) + '  ')}\n  ```")
        lines.append("")

    for slug in slugs:
        if slug in used:
            continue
        lines.append(f"- **{slug}**: (registered)")

    block = "\n".join(lines).strip()
    if len(block) > max_chars:
        return block[: max_chars - 3].rstrip() + "..."
    return block


def promote_skill_draft(folder: Path, draft_id: str) -> dict[str, Any]:
    run = read_run_meta(folder)
    row = find_skill_draft(run, draft_id)
    if row is None:
        raise ValueError("skill draft not found")
    status = str(row.get("status") or "")
    if status == "promoted":
        return row
    if status == "rejected":
        raise ValueError("skill draft was rejected")

    slug = str(row.get("slug") or "")
    draft_rel = str(row.get("draft_path") or "")
    draft_path = folder / draft_rel
    if not draft_path.is_file():
        raise ValueError("draft file missing")
    content = draft_path.read_text(encoding="utf-8")
    dest = workspace_skills_root() / slug / "SKILL.md"
    _write_text(dest, content)

    promoted_at = _now_iso()
    promoted_path = str(dest)

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        rows = skill_draft_rows(run)
        for entry in rows:
            if str(entry.get("id") or "") == draft_id:
                entry["status"] = "promoted"
                entry["promoted_at"] = promoted_at
                entry["promoted_path"] = promoted_path
        run["skill_drafts"] = rows
        return run

    patch_run_meta(folder, _patch)
    row = find_skill_draft(read_run_meta(folder), draft_id) or row
    return row


def reject_skill_draft(folder: Path, draft_id: str) -> dict[str, Any]:
    run = read_run_meta(folder)
    row = find_skill_draft(run, draft_id)
    if row is None:
        raise ValueError("skill draft not found")

    inbox_id = str(row.get("inbox_id") or "")

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        rows = skill_draft_rows(run)
        for entry in rows:
            if str(entry.get("id") or "") == draft_id:
                entry["status"] = "rejected"
        run["skill_drafts"] = rows
        return run

    patch_run_meta(folder, _patch)

    if inbox_id:
        from agent_lab.human_inbox import find_inbox_item, resolve_inbox_item

        run = read_run_meta(folder)
        item = find_inbox_item(run, inbox_id)
        if item and item.get("status") == "pending":
            resolve_inbox_item(
                folder,
                inbox_id,
                status="superseded",
                note="skill draft promote rejected",
                append_chat=False,
            )

    return find_skill_draft(read_run_meta(folder), draft_id) or row


def handle_skill_draft_inbox_resolve(
    folder: Path,
    item: dict[str, Any],
    *,
    selected: list[str] | None,
    status: str,
) -> dict[str, Any] | None:
    """Side-effect helper when inbox skill_draft is resolved."""
    if item.get("kind") != "skill_draft":
        return None
    refs = list(item.get("refs") or [])
    draft_id = refs[0] if refs else None
    if not draft_id:
        return None
    if status in {"rejected", "superseded"}:
        return reject_skill_draft(folder, str(draft_id))
    choice = (selected or [""])[0].strip().lower()
    if choice == "approve":
        return promote_skill_draft(folder, str(draft_id))
    if choice == "reject":
        return reject_skill_draft(folder, str(draft_id))
    return None
