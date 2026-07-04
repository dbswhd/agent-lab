from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AGENT_LAB_SRC = _REPO_ROOT / "src" / "agent_lab"

# Canonical on-disk / turn-end writers (F4).
_CANONICAL_WRITERS = frozenset(
    {
        "src/agent_lab/run/meta.py",
        "src/agent_lab/room/session_persist.py",
        "src/agent_lab/room/turn_meta.py",
    }
)

# In-memory mutators during a turn — must stay empty (use stamp_run_meta / update).
_KNOWN_BASELINE = frozenset()

_RUN_META_SUBSCRIPT = re.compile(r"run_meta\[")


def _files_with_run_meta_subscript() -> frozenset[str]:
    found: set[str] = set()
    for path in _AGENT_LAB_SRC.rglob("*.py"):
        rel = path.relative_to(_REPO_ROOT).as_posix()
        if rel in _CANONICAL_WRITERS:
            continue
        if _RUN_META_SUBSCRIPT.search(path.read_text(encoding="utf-8")):
            found.add(rel)
    return frozenset(found)


def test_run_meta_subscript_writes_no_new_files() -> None:
    """F4 guardrail — new run_meta[ writers require allowlist review."""
    offenders = _files_with_run_meta_subscript()
    allowed = _KNOWN_BASELINE | _CANONICAL_WRITERS
    unexpected = sorted(offenders - allowed)
    assert not unexpected, (
        "New run_meta[ subscript usage outside F4 allowlist: "
        f"{unexpected}. Prefer agent_lab.run.meta.stamp_run_meta(...). "
        "Add to _KNOWN_BASELINE only after deliberate review."
    )


def test_run_meta_baseline_matches_repo() -> None:
    """Keep baseline in sync — remove entries when run_meta[ usage is eliminated."""
    offenders = _files_with_run_meta_subscript()
    stale = sorted(_KNOWN_BASELINE - offenders)
    assert not stale, (
        "Stale F4 baseline entries (no longer use run_meta[): "
        f"{stale}. Remove from _KNOWN_BASELINE."
    )


def test_f4_allowlist_is_empty() -> None:
    """F4 ratchet complete for in-memory subscript writers."""
    assert _KNOWN_BASELINE == frozenset()
    assert _files_with_run_meta_subscript() == frozenset()
