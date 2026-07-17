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
dozen distinct producer calls. Earlier iterations of this module assumed
most of them (mailbox/team_task/objection/challenge_owner/dispatch_intent/
plugin_allowlist/thread_resume/session_skills/capability_preamble/turn_
state/plan_open/turn_bridge/peer/envelope_follow_up/agent_tool_rules) were
private, string-appender-style helpers INSIDE `bundle.py` itself — that
assumption was wrong. Every one of them is actually a standalone,
independently-callable function living in ITS OWN module (`room/tasks.py`,
`room/mailbox.py`, `room/objections.py`, `plugin_discovery.py`,
`room/agent_capabilities.py`, `agent/thread_resume.py`, `skill_drafts.py`,
`room/dispatch_intents.py`, `room/context/plan_excerpt.py`,
`room/turn_state.py`, `room/context/peer_digest.py`, `reply_policy.py`,
`room/context/constraints.py`) that `bundle.py` merely calls and string-
concatenates — exactly the same shape as `room/artifacts.py::
build_artifacts_block`, which `adapt_artifacts` already wraps. 2026-07-16
closed all of them (see `context/adapters.py`'s
`adapt_team_task_block`/`adapt_objection_block`/`adapt_challenge_owner_
block`/`adapt_plugin_allowlist_block`/`adapt_capability_preamble`/
`adapt_thread_resume_block`/`adapt_session_skills_block`/`adapt_dispatch_
intent_block`/`adapt_plan_open_block`/`adapt_turn_state_block`/`adapt_turn_
bridge_block`/`adapt_peer_block`/`adapt_envelope_follow_up_block`/`adapt_
agent_tool_rules_block`/`adapt_mailbox_messages`).

**`adapt_mailbox_messages` closes CX1 §3's `agent_opinion` gap** (so does
`adapt_turn_bridge_block`/`adapt_peer_block`): a peer Room agent's direct
mailbox message or in-turn chat is that peer's own communication, not a
system-produced fact — the CX1 registry flagged `SourceClass.AGENT_OPINION`
as having no confirmed producer; these three do.

**2026-07-16 — `recent` transcript gap closed.** The earlier assumption
that no `SourceClass` fits "the ongoing conversation" was wrong for the same
reason the other 14 were: `build_recent_turns_block`'s input is not one
opaque blob, it's a structured list of messages (`ChatMessage.to_dict()`'s
shape: `{role, agent, content, ts, parallel_round?}`). Decomposed PER
MESSAGE by `role` (`context/adapters.py::adapt_recent_messages`): `role ==
"user"` -> HUMAN_INTENT (09-context-engineering.md §12's "현재 Human intent",
literally the Human's own recent turns); `role == "agent"` and `agent ==
self_agent` -> EPISODE (this agent's own session-scoped history, distinct
from a peer's opinion); `role == "agent"` and `agent != self_agent` ->
AGENT_OPINION (same slot as mailbox/peer/bridge, for a caller that doesn't
pre-dedupe peer lines out of `messages`); `role == "system"` ->
RUNTIME_STATE.

**Still genuinely out of scope:** `_format_grounding_block` (not an
independent producer — see `context/adapters.py`'s module docstring).
`bundle.py` itself remains completely untouched by any of this (verify with
`git diff -- src/agent_lab/context/bundle.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_lab.context.activity_recipes import recipe_for
from agent_lab.context.adapters import (
    adapt_agent_tool_rules_block,
    adapt_agents_md_flat,
    adapt_agents_md_hierarchy,
    adapt_approved_plan,
    adapt_artifacts,
    adapt_capability_preamble,
    adapt_challenge_owner_block,
    adapt_clarify_facts,
    adapt_dispatch_intent_block,
    adapt_envelope_follow_up_block,
    adapt_goal_ledger,
    adapt_mailbox_messages,
    adapt_mission_notepad,
    adapt_objection_block,
    adapt_peer_block,
    adapt_plan_open_block,
    adapt_playbook_bullets,
    adapt_plugin_allowlist_block,
    adapt_project_md,
    adapt_recent_messages,
    adapt_repo_tree,
    adapt_reply_policy_guidance,
    adapt_session_guidance,
    adapt_session_skills_block,
    adapt_shared_context_md,
    adapt_team_task_block,
    adapt_thread_resume_block,
    adapt_turn_bridge_block,
    adapt_turn_state_block,
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
    project_md: str = ""
    project_md_mtime: float | None = None
    agents_md_flat: str = ""
    agents_md_flat_mtime: float | None = None
    shared_context_md: str = ""
    reply_policy_guidance_parts: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    team_task_block: str = ""
    objection_block: str = ""
    challenge_owner_block: str = ""
    plugin_allowlist_block: str = ""
    capability_preamble: str = ""
    thread_resume_block: str = ""
    session_skills_block: str = ""
    dispatch_intent_block: str = ""
    plan_open_block: str = ""
    turn_state_block: str = ""
    turn_bridge_block: str = ""
    peer_block: str = ""
    envelope_follow_up_block: str = ""
    agent_tool_rules_block: str = ""
    mailbox_messages: list[dict[str, Any]] = field(default_factory=list)
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    self_agent: str = ""


def build_manifest_via_recipe(activity: ActivityKind, inputs: RecipeBundleInputs) -> ContextManifest:
    """Adapts `inputs` into `ContextItem`s via the already-shipped CX1
    adapters, then runs `select_context()` against `activity_recipes.py`'s
    recipe for `activity`. Raises `ContextSelectionError` exactly as
    `select_context()` would for any other caller — in particular,
    CRITIC/REPAIR/SCRIBE need `inputs.artifacts` non-empty to satisfy their
    EVIDENCE requirement; without it they still raise "missing required
    sources"."""
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
    if (item := adapt_project_md(inputs.project_md, mtime=inputs.project_md_mtime)) is not None:
        items.append(item)
    if (item := adapt_agents_md_flat(inputs.agents_md_flat, mtime=inputs.agents_md_flat_mtime)) is not None:
        items.append(item)
    if (item := adapt_shared_context_md(inputs.shared_context_md)) is not None:
        items.append(item)
    items.extend(adapt_reply_policy_guidance(inputs.reply_policy_guidance_parts))
    items.extend(adapt_artifacts(inputs.artifacts))
    if (item := adapt_team_task_block(inputs.team_task_block)) is not None:
        items.append(item)
    if (item := adapt_objection_block(inputs.objection_block)) is not None:
        items.append(item)
    if (item := adapt_challenge_owner_block(inputs.challenge_owner_block)) is not None:
        items.append(item)
    if (item := adapt_plugin_allowlist_block(inputs.plugin_allowlist_block)) is not None:
        items.append(item)
    if (item := adapt_capability_preamble(inputs.capability_preamble)) is not None:
        items.append(item)
    if (item := adapt_thread_resume_block(inputs.thread_resume_block)) is not None:
        items.append(item)
    if (item := adapt_session_skills_block(inputs.session_skills_block)) is not None:
        items.append(item)
    if (item := adapt_dispatch_intent_block(inputs.dispatch_intent_block)) is not None:
        items.append(item)
    if (item := adapt_plan_open_block(inputs.plan_open_block)) is not None:
        items.append(item)
    if (item := adapt_turn_state_block(inputs.turn_state_block)) is not None:
        items.append(item)
    if (item := adapt_turn_bridge_block(inputs.turn_bridge_block)) is not None:
        items.append(item)
    if (item := adapt_peer_block(inputs.peer_block)) is not None:
        items.append(item)
    if (item := adapt_envelope_follow_up_block(inputs.envelope_follow_up_block)) is not None:
        items.append(item)
    if (item := adapt_agent_tool_rules_block(inputs.agent_tool_rules_block)) is not None:
        items.append(item)
    items.extend(adapt_mailbox_messages(inputs.mailbox_messages))
    items.extend(adapt_recent_messages(inputs.recent_messages, self_agent=inputs.self_agent))

    need = recipe_for(activity)
    return select_context(need, tuple(items))
