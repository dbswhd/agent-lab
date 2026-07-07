"""N6 — self-patch meta-loop infrastructure: allowlist + eligibility classification.

See NORTH-STAR §2.1 N6. Room can eventually propose improvements to agent-lab's
own codebase (a dogfood loop); this module is the *first commit* of that
initiative — the allowlist scoping the paths a self-patch is ever allowed to
touch, and a pure classifier that tags whether a set of touched paths falls
entirely inside it.

Scope (deliberately conservative — "인프라의 정례화", not automation):
- This module does not apply patches, does not create Inbox items, and does
  not change any gate/approval behavior. Every execution — allowlisted or
  not — still goes through the exact same worktree + Oracle + Human Inbox
  gate it does today (NORTH-STAR §6 mote: Human Inbox unchanged).
- Its only effect is observability: `outcome_harvester.record_execute_outcome`
  stamps the classification onto the outcome ledger row so a future
  autonomy-ladder rule has something concrete to key off of — the same
  "measure first, automate later" discipline as S1's RECORD phase.
- Core logic (`src/agent_lab/**` outside the allowlist) is never eligible —
  this is enforced structurally by the allowlist not listing it, not by a
  separate special case here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_ALLOWLIST_RELPATH = Path(".agent-lab") / "self_patch_allowlist.txt"

_DEFAULT_ALLOWLIST: tuple[str, ...] = (
    ".claude/skills/**",
    "src/agent_lab/agents/prompts.py",
    "src/agent_lab/run/profile.py",
)


def self_patch_allowlist_path(root: Path | None = None) -> Path:
    if root is None:
        from agent_lab.outcome_harvester import outcomes_path

        root = outcomes_path().parent.parent
    return Path(root) / _ALLOWLIST_RELPATH


def ensure_self_patch_allowlist(root: Path | None = None) -> Path:
    """Create the allowlist file with the documented initial patterns if absent."""
    path = self_patch_allowlist_path(root)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# N6 self-patch allowlist (NORTH-STAR §2.1) — one glob pattern per line.\n"
            "# Only paths matching a pattern here are ever eligible for self-patch\n"
            "# classification. Everything else (core src/agent_lab/** logic) always\n"
            "# requires the full Human gate — this file does not weaken that.\n"
            "# '**' matches any depth; '*' matches within one path segment.\n"
        )
        path.write_text(header + "\n".join(_DEFAULT_ALLOWLIST) + "\n", encoding="utf-8")
    return path


def load_self_patch_allowlist(root: Path | None = None) -> list[str]:
    """Read allowlist patterns (blank lines and ``#`` comments skipped)."""
    path = self_patch_allowlist_path(root)
    if not path.is_file():
        return list(_DEFAULT_ALLOWLIST)
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return patterns


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Gitignore-style glob: '**' matches any depth, '*' stays within one segment."""
    placeholder = "\x00DOUBLESTAR\x00"
    escaped = re.escape(pattern.strip("/")).replace(re.escape("**"), placeholder)
    escaped = escaped.replace(re.escape("*"), "[^/]*")
    escaped = escaped.replace(placeholder, ".*")
    return re.compile(f"^{escaped}$")


def _normalize(path: str) -> str:
    return str(path).strip().replace("\\", "/").lstrip("/")


def matches_self_patch_allowlist(path: str, patterns: list[str] | None = None, *, root: Path | None = None) -> bool:
    """True if ``path`` (repo-relative) matches at least one allowlist pattern."""
    pats = patterns if patterns is not None else load_self_patch_allowlist(root)
    norm = _normalize(path)
    return any(_pattern_to_regex(p).match(norm) for p in pats)


def classify_self_patch(touched_paths: list[str], *, root: Path | None = None) -> dict[str, Any]:
    """Pure classification — no I/O beyond reading the allowlist, no side effects.

    ``eligible`` is True only when every touched path matches the allowlist —
    a single core-path touch disqualifies the whole set (self-patch is an
    all-or-nothing classification per execution, not per-file).
    """
    patterns = load_self_patch_allowlist(root)
    if not touched_paths:
        return {"eligible": False, "matched": [], "core_paths": [], "patterns": patterns}

    matched: list[str] = []
    core_paths: list[str] = []
    for path in touched_paths:
        if matches_self_patch_allowlist(path, patterns):
            matched.append(path)
        else:
            core_paths.append(path)

    return {
        "eligible": not core_paths,
        "matched": matched,
        "core_paths": core_paths,
        "patterns": patterns,
    }


__all__ = [
    "self_patch_allowlist_path",
    "ensure_self_patch_allowlist",
    "load_self_patch_allowlist",
    "matches_self_patch_allowlist",
    "classify_self_patch",
]
