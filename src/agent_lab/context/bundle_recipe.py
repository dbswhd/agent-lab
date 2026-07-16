"""CX8 (09-context-engineering.md §11) — first flag-gated slice of the
select_context() convergence path for `context/bundle.py`'s legacy
string-concatenation assembler.

**Not wired into the live per-turn call path.** `build_context_bundle` is
completely untouched by this module. This is a standalone, independently
callable function that computes a parallel, typed `ContextManifest` from the
SAME already-adapted producers `context/adapters.py` wraps, so a dogfood
harness or eval script can compare it against the legacy bundle's output —
the first concrete step toward CX8's "agent invocation마다 context assembly
path가 하나다" acceptance criterion, not the cutover itself. Actually
splicing this into `build_context_bundle` (behind `AGENT_LAB_CONTEXT_RECIPE`,
already registered in `runtime_flags.py`/`run/profile.py`) is a follow-up
step gated on parity results from this slice, per the CX8 discussion in
09-context-engineering.md.

**Scope of this slice, deliberately narrow.** `bundle.py` makes roughly two
dozen distinct producer calls, but most of them (mailbox/team_task/
objection/challenge_owner/gate_snapshot/dispatch_intent/plugin_allowlist/
thread_resume/session_skills/capability_preamble, plus the recent/peer/
bridge/turn_state message-history fields) are private, string-appender-style
helpers inside `bundle.py` itself — they mutate/append to an in-progress
`constraints` string rather than returning an independently callable value,
so wiring them here would mean refactoring `bundle.py`'s internals first,
which is out of scope for a slice that must not touch the live path. This
module only covers producers that are BOTH already adapted (see
`context/adapters.py`) AND cleanly callable on their own: session guidance,
clarify facts, goal ledger, mission notepad, repo tree, wisdom index hits,
playbook bullets, AGENTS.md hierarchy, reply-policy guidance parts, and
`plan_md` (via the new `adapt_approved_plan`, added specifically for this
slice since CX1's registry never catalogued a producer for
`SourceClass.APPROVED_PLAN` even though every activity recipe except CLARIFY
requires it).

**A real, currently-unclosed gap:** no adapter exists yet for
`SourceClass.EVIDENCE`. That means CRITIC/REPAIR/SCRIBE — whose recipes all
require EVIDENCE — can never successfully build a manifest through this
slice; `build_manifest_via_recipe` will raise "missing required sources" for
those activities every time. Only CLARIFY, PLAN, and EXECUTE recipes can
currently be satisfied. This isn't hidden or worked around here; the
follow-up (adapting `build_artifacts_block`'s output, the closest existing
EVIDENCE-shaped producer in `bundle.py`) is a separate, explicitly tracked
next step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_lab.context.activity_recipes import recipe_for
from agent_lab.context.adapters import (
    adapt_agents_md_hierarchy,
    adapt_approved_plan,
    adapt_clarify_facts,
    adapt_goal_ledger,
    adapt_mission_notepad,
    adapt_playbook_bullets,
    adapt_repo_tree,
    adapt_reply_policy_guidance,
    adapt_session_guidance,
    adapt_wisdom_index_hits,
)
from agent_lab.context.recipe import ActivityKind, ContextItem, ContextManifest, select_context
from agent_lab.wisdom.playbook import PlaybookBullet

# Mission phase -> ActivityKind. `mission/loop.py`'s MissionPhase is the only
# genuinely activity-shaped state machine in the codebase today, but it
# doesn't cover every ActivityKind and several phases don't correspond to any
# activity at all -- both gaps are intentional, not oversights:
#
# - DISCUSS/PLAN_GATE/PLAN_REJECT all map to PLAN: this is exactly the same
#   phase set `layers.py::should_use_mission_slim_bundle` already uses to
#   trigger bundle.py's own hand-rolled "lighter context for planning" gate,
#   so the mapping isn't inventing a new grouping.
# - MERGE_REVIEW/VERIFY map to CRITIC (closest fit: independent verification
#   against acceptance criteria) -- a judgment call, not a settled one.
# - MISSION_DEFINE/MISSION_PAUSED/MISSION_DONE map to nothing: bootstrapping,
#   paused, and terminal states aren't "activities" a context recipe applies
#   to.
# - SCRIBE has no corresponding phase at all -- scribe context is built
#   through a wholly separate, unconverged path (`core/limits.py`'s
#   `ScribeContextLimits`), not through bundle.py's mission_loop-gated flow.
_PHASE_TO_ACTIVITY: dict[str, ActivityKind] = {
    "CLARIFY": ActivityKind.CLARIFY,
    "DISCUSS": ActivityKind.PLAN,
    "PLAN_GATE": ActivityKind.PLAN,
    "PLAN_REJECT": ActivityKind.PLAN,
    "EXECUTE_QUEUE": ActivityKind.EXECUTE,
    "DRY_RUN": ActivityKind.EXECUTE,
    "MERGE_REVIEW": ActivityKind.CRITIC,
    "VERIFY": ActivityKind.CRITIC,
    "REPAIR": ActivityKind.REPAIR,
}


def activity_kind_for_mission_phase(phase: str) -> ActivityKind | None:
    """Returns None for phases with no activity-kind mapping (see the
    module-level table's docstring for which ones and why) -- callers must
    handle None by falling back to the legacy bundle.py path entirely, since
    there's no recipe to select against."""
    return _PHASE_TO_ACTIVITY.get(phase)


@dataclass(frozen=True, slots=True)
class RecipeBundleInputs:
    """Raw producer output a caller has ALREADY computed, mirroring
    adapters.py's own "take already-computed output" philosophy — this
    module doesn't call any producer function itself, callers own invoking
    `build_session_guidance_block`, `search_wisdom_index`, etc. and passing
    results in. Every field defaults empty because not every activity/turn
    calls every producer (bundle.py's own conditional gating — R1-only
    wisdom search, playbook only with a non-empty topic, mission wisdom
    only mid-mission — is the caller's responsibility to replicate, not
    this module's)."""

    plan_md: str = ""
    session_guidance: str = ""
    clarify_facts: list[dict[str, Any]] = field(default_factory=list)
    goal_ledger: list[dict[str, Any]] = field(default_factory=list)
    mission_notepad: str = ""
    mission_notepad_session_id: str = ""
    repo_tree: str = ""
    repo_tree_commit_sha: str | None = None
    wisdom_index_hits: list[dict[str, Any]] = field(default_factory=list)
    playbook_bullets: list[PlaybookBullet] = field(default_factory=list)
    agents_md_hierarchy: str = ""
    reply_policy_guidance_parts: list[str] = field(default_factory=list)


def build_manifest_via_recipe(activity: ActivityKind, inputs: RecipeBundleInputs) -> ContextManifest:
    """Adapts `inputs` into `ContextItem`s via the already-shipped CX1
    adapters, then runs `select_context()` against `activity_recipes.py`'s
    recipe for `activity`. Raises `ContextSelectionError` exactly as
    `select_context()` would for any other caller — in particular, for
    CRITIC/REPAIR/SCRIBE this will currently always raise "missing required
    sources" for `SourceClass.EVIDENCE` (see module docstring)."""
    items: list[ContextItem] = []

    if (item := adapt_approved_plan(inputs.plan_md)) is not None:
        items.append(item)
    if (item := adapt_session_guidance(inputs.session_guidance)) is not None:
        items.append(item)
    items.extend(adapt_clarify_facts(inputs.clarify_facts))
    items.extend(adapt_goal_ledger(inputs.goal_ledger))
    if (item := adapt_mission_notepad(inputs.mission_notepad, session_id=inputs.mission_notepad_session_id)) is not None:
        items.append(item)
    if (item := adapt_repo_tree(inputs.repo_tree, commit_sha=inputs.repo_tree_commit_sha)) is not None:
        items.append(item)
    items.extend(adapt_wisdom_index_hits(inputs.wisdom_index_hits))
    items.extend(adapt_playbook_bullets(inputs.playbook_bullets))
    if (item := adapt_agents_md_hierarchy(inputs.agents_md_hierarchy)) is not None:
        items.append(item)
    items.extend(adapt_reply_policy_guidance(inputs.reply_policy_guidance_parts))

    need = recipe_for(activity)
    return select_context(need, tuple(items))
