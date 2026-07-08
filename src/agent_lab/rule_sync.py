"""N10b — Rule Sync: export Human-approved correction rules to other harnesses.

See docs/N10-USER-LOOP-WISDOM-DRAFT.md §2 (N10b). N10a's Correction Harvester
accumulates approved rules into a single repo-local SSOT
(``.agent-lab/wisdom/correction_rules.md``, ``correction_harvester.py``). This
module is the one-way export from that SSOT into the formats each harness
actually reads: Claude Code (``.claude/rules/*.md``), Cursor
(``.cursor/rules/*.mdc``), and Codex (``~/.codex/AGENTS.md``).

Safety (NORTH-STAR §6 mote check — this is the one N10-family piece with
external blast radius: Codex's target is a real global file used by every
other project on the machine, not something scoped to this repo):
- Default OFF (``AGENT_LAB_RULE_SYNC``) — unlike the other N10-family flags,
  this one writes outside the session/repo, so it does not opt in silently.
- ``apply_rule_sync`` never runs unattended — it is only ever invoked from a
  Human Inbox approval (see ``correction_harvester``'s resolve dispatch),
  never automatically after a rule is promoted.
- Writes are confined to a delimited, idempotent managed section
  (``_MARKER_START``/``_MARKER_END``) — re-syncing replaces only that section,
  never touching hand-written content elsewhere in the target file.
- ``codex_home`` is always overridable (never a bare ``Path.home()`` call
  buried in a write path) so tests — and a cautious human — can point it at a
  throwaway location before trusting it against the real ``~/.codex``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from agent_lab.env_flags import env_bool
from agent_lab.run.state import RunStateLike

_RULE_BLOCK = re.compile(
    r"^##\s+(?P<label>.+?)\s+\(`(?P<key>[^`]+)`\)\s*\n+"
    r"(?P<text>.+?)\n+"
    r"-\s*근거:\s*(?P<evidence>.+?)\s*\n"
    r"-\s*승인일:\s*(?P<approved_at>.+?)\s*(?:\n|$)",
    re.MULTILINE | re.DOTALL,
)

_MARKER_START = "<!-- agent-lab:correction-rules:start -->"
_MARKER_END = "<!-- agent-lab:correction-rules:end -->"

_CLAUDE_RULES_RELPATH = Path(".claude/rules/correction-rules.md")
_CURSOR_RULES_RELPATH = Path(".cursor/rules/correction-rules.mdc")


def rule_sync_enabled() -> bool:
    return env_bool("AGENT_LAB_RULE_SYNC")


def _ssot_path(root: Path | None) -> Path:
    from agent_lab.correction_harvester import _RULES_RELPATH

    if root is None:
        from agent_lab.outcome_harvester import outcomes_path

        root = outcomes_path().parent.parent
    return Path(root) / _RULES_RELPATH


def parse_correction_rules(root: Path | None = None) -> list[dict[str, str]]:
    """Parse the N10a SSOT markdown into structured rule rows (read-only)."""
    path = _ssot_path(root)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, str]] = []
    for m in _RULE_BLOCK.finditer(text):
        rows.append(
            {
                "label": m.group("label").strip(),
                "key": m.group("key").strip(),
                "text": m.group("text").strip(),
                "evidence": m.group("evidence").strip(),
                "approved_at": m.group("approved_at").strip(),
            }
        )
    return rows


def _managed_section(rules: list[dict[str, str]]) -> str:
    lines = ["", _MARKER_START, ""]
    for rule in rules:
        lines.append(f"- **{rule['label']}** (`{rule['key']}`): {rule['text']}")
    lines.extend(["", _MARKER_END, ""])
    return "\n".join(lines)


def _replace_managed_section(existing: str, section: str) -> str:
    if _MARKER_START in existing and _MARKER_END in existing:
        start = existing.index(_MARKER_START)
        end = existing.index(_MARKER_END) + len(_MARKER_END)
        return existing[:start].rstrip() + section.rstrip() + "\n" + existing[end:].lstrip("\n")
    return existing.rstrip() + "\n" + section.rstrip() + "\n"


def render_claude_rules(rules: list[dict[str, str]], existing: str = "") -> str:
    header = "# Correction Rules (N10b — synced from N10a Correction Harvester)\n"
    base = existing if existing.strip() else header
    return _replace_managed_section(base, _managed_section(rules))


def render_cursor_rules(rules: list[dict[str, str]], existing: str = "") -> str:
    header = (
        "---\n"
        "description: Human-approved correction rules synced from Claude Code (N10a/N10b)\n"
        "alwaysApply: true\n"
        "---\n\n"
        "# Correction Rules\n"
    )
    base = existing if existing.strip() else header
    return _replace_managed_section(base, _managed_section(rules))


def render_codex_agents_md(rules: list[dict[str, str]], existing: str = "") -> str:
    base = existing  # AGENTS.md may already carry hand-written global instructions — never overwrite those
    return _replace_managed_section(base, _managed_section(rules))


_RENDERERS = {
    "claude": (render_claude_rules, _CLAUDE_RULES_RELPATH),
    "cursor": (render_cursor_rules, _CURSOR_RULES_RELPATH),
}


def default_codex_home() -> Path:
    return Path(os.getenv("AGENT_LAB_CODEX_HOME") or (Path.home() / ".codex"))


def preview_rule_sync(
    root: Path | None = None,
    *,
    targets: list[str] | None = None,
    codex_home: Path | None = None,
) -> dict[str, Any]:
    """Compute what each target file would become — no writes (dry-run)."""
    rules = parse_correction_rules(root)
    targets = targets or ["claude", "cursor", "codex"]
    repo_root = _ssot_path(root).parent.parent.parent  # .agent-lab/wisdom/x.md -> repo root
    plan: dict[str, Any] = {"rules": rules, "targets": {}}

    for name, (renderer, relpath) in _RENDERERS.items():
        if name not in targets:
            continue
        path = repo_root / relpath
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        plan["targets"][name] = {"path": str(path), "content": renderer(rules, existing)}

    if "codex" in targets:
        home = codex_home or default_codex_home()
        path = home / "AGENTS.md"
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        plan["targets"]["codex"] = {"path": str(path), "content": render_codex_agents_md(rules, existing)}

    return plan


def apply_rule_sync(
    root: Path | None = None,
    *,
    targets: list[str] | None = None,
    codex_home: Path | None = None,
) -> dict[str, Any]:
    """Write the synced rule files — only ever called from a Human Inbox approval."""
    plan = preview_rule_sync(root, targets=targets, codex_home=codex_home)
    written: list[str] = []
    for target in plan["targets"].values():
        path = Path(target["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(target["content"], encoding="utf-8")
        written.append(str(path))
    return {"rules": plan["rules"], "written": written}


def _pending_rule_sync_proposal(run_meta: RunStateLike) -> bool:
    for item in run_meta.get("human_inbox") or []:
        if isinstance(item, dict) and item.get("kind") == "rule_sync" and item.get("status") == "pending":
            return True
    return False


def maybe_propose_rule_sync(folder: Path, *, root: Path | None = None) -> dict[str, Any] | None:
    """Human Inbox proposal after a correction rule is promoted (fail-open, opt-in only).

    Never writes anything itself — only offers the option. A pending proposal
    is not duplicated; declining once does not reappear for the same rule set
    (dedup mirrors the other N10-family Inbox proposals).
    """
    try:
        if not rule_sync_enabled():
            return None
        from agent_lab.human_inbox import create_inbox_item
        from agent_lab.run.meta import read_run_meta

        run_meta = read_run_meta(folder)
        if _pending_rule_sync_proposal(run_meta):
            return None
        rules = parse_correction_rules(root)
        if not rules:
            return None
        names = ", ".join(r["label"] for r in rules[:3])
        return create_inbox_item(
            folder,
            kind="rule_sync",
            source="rule_sync",
            prompt=f"승인된 교정 규칙({names})을 Cursor/Codex 전역 설정에도 반영할까요?",
            summary=f"{len(rules)}개 규칙 → .claude/rules, .cursor/rules, ~/.codex/AGENTS.md",
            options=[
                {"id": "approve", "label": "다른 도구에도 반영"},
                {"id": "reject", "label": "이 리포에만 유지"},
            ],
            refs=[r["key"] for r in rules],
        )
    except Exception:  # fail-open: sync proposal must never block rule promotion
        import logging

        logging.getLogger(__name__).warning("maybe_propose_rule_sync failed for %s", folder, exc_info=True)
        return None


def handle_rule_sync_inbox_resolve(
    folder: Path,
    item: dict[str, Any],
    *,
    selected: list[str] | None,
    status: str,
    root: Path | None = None,
) -> None:
    """Side-effect helper when inbox rule_sync is resolved — the only path that writes files."""
    if item.get("kind") != "rule_sync":
        return
    if status in ("rejected", "superseded"):
        return
    choice = (selected or [""])[0].strip().lower()
    if choice != "approve":
        return
    apply_rule_sync(root)


__all__ = [
    "rule_sync_enabled",
    "parse_correction_rules",
    "render_claude_rules",
    "render_cursor_rules",
    "render_codex_agents_md",
    "preview_rule_sync",
    "apply_rule_sync",
    "maybe_propose_rule_sync",
    "handle_rule_sync_inbox_resolve",
    "default_codex_home",
]
