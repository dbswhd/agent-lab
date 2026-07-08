"""N6 — self-patch meta-loop infrastructure: allowlist + eligibility classification.

See NORTH-STAR §2.1 N6. Room can eventually propose improvements to agent-lab's
own codebase (a dogfood loop); this module is the *first commit* of that
initiative — a pure classifier that tags whether a set of touched paths falls
entirely inside the editable-surface allowlist.

Scope (deliberately conservative — "인프라의 정례화", not automation):
- This module does not apply patches, does not create Inbox items, and does
  not change any gate/approval behavior. Every execution — allowlisted or
  not — still goes through the exact same worktree + Oracle + Human Inbox
  gate it does today (NORTH-STAR §6 mote: Human Inbox unchanged).
- Its only effect is observability: `outcome_harvester.record_execute_outcome`
  stamps the classification onto the outcome ledger row so a future
  autonomy-ladder rule has something concrete to key off of — the same
  "measure first, automate later" discipline as S1's RECORD phase.
- Core logic (outside the allowlist) is never eligible — this is enforced
  structurally by the allowlist not listing it, not by a separate special
  case here.

HS3-2 unification (2026-07-09): the allowlist is now Tier A of
``harness_proposer.py``'s ``.agent-lab/harness/manifest.json`` — a single
git-tracked SSOT shared with the PROPOSE pipeline, replacing the standalone
``self_patch_allowlist.txt`` this module used to maintain independently
(NORTH-STAR §16 risk R4: "allowlist/manifest 이중").
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.harness_proposer import (
    classify_tier,
    normalize_path as _normalize,  # noqa: F401 — re-exported for existing callers
    tier_a_globs,
)


def load_self_patch_allowlist(root: Path | None = None) -> list[str]:
    """Tier A globs from the harness manifest (see module docstring)."""
    return tier_a_globs(root=root)


def matches_self_patch_allowlist(path: str, patterns: list[str] | None = None, *, root: Path | None = None) -> bool:
    """True if ``path`` (repo-relative) matches at least one allowlist pattern.

    When ``patterns`` is omitted, resolves via the manifest (Tier A only) —
    equivalent to ``classify_tier(path, root=root) == "A"`` but also usable
    against an arbitrary explicit pattern list for testing.
    """
    if patterns is not None:
        from agent_lab.harness_proposer import _pattern_to_regex

        norm = _normalize(path)
        return any(_pattern_to_regex(p).match(norm) for p in patterns)
    return classify_tier(path, root=root) == "A"


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
    "load_self_patch_allowlist",
    "matches_self_patch_allowlist",
    "classify_self_patch",
]
