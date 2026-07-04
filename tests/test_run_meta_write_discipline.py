from __future__ import annotations

import re
from pathlib import Path

import pytest

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

# In-memory mutators during a turn — F4 debt; shrink via allowlist PRs, do not grow.
_KNOWN_BASELINE = frozenset(
    {
        "src/agent_lab/plan/workflow.py",
        "src/agent_lab/debate_convergence.py",
        "src/agent_lab/room/turn_flow.py",
        "src/agent_lab/role_plan.py",
        "src/agent_lab/room/agent_capabilities.py",
        "src/agent_lab/room/turn_flow_setup.py",
        "src/agent_lab/room/turn_routing.py",
        "src/agent_lab/context/bundle.py",
        "src/agent_lab/token_budget.py",
        "src/agent_lab/room/agent_invoke.py",
        "src/agent_lab/room/turn_flow_support.py",
        "src/agent_lab/mission/board.py",
        "src/agent_lab/room/team_orchestration.py",
        "src/agent_lab/inbox/harvest.py",
        "src/agent_lab/cost_ledger.py",
        "src/agent_lab/plan/paths.py",
        "src/agent_lab/room/turn_flow_rounds.py",
        "src/agent_lab/session/guidance.py",
        "src/agent_lab/room/turn_policy.py",
        "src/agent_lab/room/dispatch.py",
        "src/agent_lab/room/tasks.py",
        "src/agent_lab/room/mailbox.py",
        "src/agent_lab/room/artifacts.py",
        "src/agent_lab/room/turn_state.py",
        "src/agent_lab/mission/tick.py",
        "src/agent_lab/plugin_discovery.py",
        "src/agent_lab/room/objections.py",
        "src/agent_lab/room/dispatch_intents.py",
        "src/agent_lab/agent/availability.py",
        "src/agent_lab/consensus_gate.py",
    }
)

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
        f"{unexpected}. Add to _KNOWN_BASELINE only after deliberate review."
    )


def test_run_meta_baseline_matches_repo() -> None:
    """Keep baseline in sync — remove entries when run_meta[ usage is eliminated."""
    offenders = _files_with_run_meta_subscript()
    stale = sorted(_KNOWN_BASELINE - offenders)
    assert not stale, (
        "Stale F4 baseline entries (no longer use run_meta[): "
        f"{stale}. Remove from _KNOWN_BASELINE."
    )
