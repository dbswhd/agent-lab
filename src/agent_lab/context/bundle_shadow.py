"""CX8 (09-context-engineering.md §11) — flag-gated shadow-parity pass,
spliced into `context/bundle.py::build_context_bundle`'s tail.

**Never changes what `build_context_bundle` returns.** This module computes
a parallel `ContextManifest` (via `context/bundle_recipe.py`) from the SAME
already-computed local values `build_context_bundle` produced for its own
legacy string bundle, and returns a comparison record for later dogfood/eval
review. Any failure in here — a missing activity mapping, a
`ContextSelectionError`, an unexpected producer shape — is caught and
returned as a `{"ok": False, ...}` record, never raised: the live per-turn
path must be unaffected regardless of what this module does. The one call
site (`build_context_bundle`) additionally gates the whole thing behind
`AGENT_LAB_CONTEXT_RECIPE` (default off) BEFORE even importing this module,
so the "off" cost is a single env-var check.

**Reuses ~14 already-computed locals instead of re-invoking their
producers**: `session_guidance`, `session_skills`, thread-resume,
plugin-allowlist, capability-preamble, team-task, objection,
challenge-owner, plan-open, turn-state, turn-bridge, peer,
envelope-follow-up, agent-tool-rules, and the recent message list —
`build_context_bundle` already built these exact strings/lists before this
module ever runs; passing them through is both cheaper and more accurate
than calling the underlying functions a second time.

**Eight producers ARE re-invoked**, because `build_context_bundle` never
exposes them as separate locals — they're merged into `constraints` by
private helpers (`_append_mission_track_c_blocks`, `_format_clarity_facts`,
`_format_decision_ledger`) before this module runs: repo tree, mission
notepad, AGENTS.md hierarchy, clarify facts, goal ledger, PROJECT.md,
AGENTS.md (flat), SHARED_CONTEXT.md. All eight are read-only, side-effect-
free calls — consistent with `bundle_recipe.py`'s own "caller invokes the
real producer directly" design. (2026-07-16 — the last three were added
after an expanded dogfood run surfaced that PROJECT_DOC coverage silently
depended entirely on `agents_md_hierarchy`, which itself only resolves
content when `plan_md` has file-path hints; a caller with a real workspace
but a hint-free plan_md previously got zero PROJECT_DOC representation.
See `docs/redesign-2026-07/evidence/cx8-context-recipe-shadow-dogfood-
2026-07-16.md`.)

**Two producers are deliberately NOT included in this pass**:
- `mailbox_messages` — `adapt_mailbox_messages` needs the UNREAD rows
  (`room/mailbox.py::unread_for_agent`), but by the time this module runs,
  `build_context_bundle` has already called `build_mailbox_block`, which
  has a side effect (`mark_delivered`) that marks those same messages read.
  Calling `unread_for_agent` again here would just return an empty list.
  Capturing mailbox rows correctly would require reading BEFORE
  `build_mailbox_block` runs — a real limitation of splicing only at the
  tail of the function, not something this module papers over.
- `wisdom_index_hits`/`playbook_bullets` — optional-only, R1-and-topic-gated
  producers; omitted for this first parity pass to keep the re-invoked set
  small. A future pass can add them once the R1/topic gating is worth
  replicating here too.

Both omissions mean this shadow manifest UNDER-represents what the full
recipe pipeline could include — a known, documented gap in this pass, not a
silent inaccuracy. `reply_policy_guidance_parts` also has one harmless
imprecision: `guidance_parts` (as `build_context_bundle` computes it) may
already have `dispatch_block`'s text appended as its last element (bundle.py
line ~657) before this module receives it, while `dispatch_intent_block`
ALSO receives that same `dispatch_block` text directly — `select_context()`'s
own exact-content dedup (§7.2 trim step 1) collapses the resulting
duplicate automatically, so it costs nothing correctness-wise, but it's
worth knowing this module doesn't bother splitting the two apart itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.context.bundle_recipe import (
    RecipeBundleInputs,
    activity_kind_for_mission_phase,
    build_manifest_via_recipe,
)
from agent_lab.core.context_bundle import ContextBundle
from agent_lab.run.state import RunStateLike


def _recent_message_dicts(recent_msgs: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": getattr(m, "role", ""),
            "agent": getattr(m, "agent", None),
            "content": getattr(m, "content", ""),
            "ts": getattr(m, "ts", None),
            "parallel_round": getattr(m, "parallel_round", None),
        }
        for m in recent_msgs
    ]


def shadow_compare_bundle(
    *,
    run_meta: RunStateLike | None,
    agent: str,
    topic: str,
    plan_md: str,
    parallel_round: int,
    session_guidance: str,
    session_skills: str,
    resume_block: str,
    plugin_block: str,
    cap_block: str,
    team_block: str,
    objection_block: str,
    challenge_block: str,
    plan_open: str,
    turn_state_block: str,
    bridge_block: str,
    peer_block: str,
    guidance_parts: list[str],
    envelope_block: str,
    tool_rules: str,
    recent_msgs: list[Any],
    legacy_bundle: ContextBundle,
) -> dict[str, Any] | None:
    """Returns a comparison dict — `{"ok": True, ...}` on success,
    `{"ok": False, ...}` on any failure (never raises). `topic`/`run_meta`
    are only used to derive the activity and re-invoke the five producers
    build_context_bundle doesn't expose as locals (see module docstring)."""
    phase = ""
    try:
        mission_loop = (run_meta or {}).get("mission_loop") if isinstance(run_meta, dict) else None
        phase = str((mission_loop or {}).get("phase") or "") if isinstance(mission_loop, dict) else ""
        activity = activity_kind_for_mission_phase(phase)
        if activity is None:
            return {"ok": False, "skipped": True, "reason": f"no activity mapping for phase {phase!r}"}

        from agent_lab.clarity import established_facts
        from agent_lab.mission.notepad import build_mission_wisdom_block
        from agent_lab.project_memory import project_md_path
        from agent_lab.repo_tree_context import build_repo_tree_block
        from agent_lab.room.artifacts import recent_artifacts_for_agent
        from agent_lab.workspace.md import (
            read_agents_md_for_injection,
            read_agents_md_hierarchy_for_injection,
            read_shared_context_for_injection,
        )

        # PROJECT.md's actual read path (session/guidance.py::_read_project_md)
        # is private, invoked only inside build_session_guidance_block -- no
        # standalone producer exists to call independently (the same reason
        # adapt_project_md takes already-read content, agnostic to how it was
        # read). Read the file directly here, mirroring bootstrap_project_md/
        # _read_project_md's own path convention.
        project_md_content = ""
        project_md_mtime: float | None = None
        workspace_binding = (run_meta or {}).get("workspace_binding") if isinstance(run_meta, dict) else None
        workspace_path = workspace_binding.get("path") if isinstance(workspace_binding, dict) else None
        if workspace_path:
            candidate = project_md_path(Path(str(workspace_path)).expanduser())
            if candidate.is_file():
                project_md_content = candidate.read_text(encoding="utf-8")
                project_md_mtime = candidate.stat().st_mtime

        inputs = RecipeBundleInputs(
            plan_md=plan_md,
            session_guidance=session_guidance,
            clarify_facts=established_facts(run_meta) if isinstance(run_meta, dict) else [],
            goal_ledger=list((run_meta or {}).get("goal_ledger") or []) if isinstance(run_meta, dict) else [],
            mission_notepad=build_mission_wisdom_block(run_meta),
            repo_tree=build_repo_tree_block(run_meta),
            agents_md_hierarchy=read_agents_md_hierarchy_for_injection(run_meta or {}, plan_md),
            project_md=project_md_content,
            project_md_mtime=project_md_mtime,
            agents_md_flat=read_agents_md_for_injection(run_meta or {}),
            shared_context_md=read_shared_context_for_injection(run_meta or {}),
            reply_policy_guidance_parts=guidance_parts,
            artifacts=recent_artifacts_for_agent(run_meta, agent, parallel_round=parallel_round),
            team_task_block=team_block,
            objection_block=objection_block,
            challenge_owner_block=challenge_block,
            plugin_allowlist_block=plugin_block,
            capability_preamble=cap_block,
            thread_resume_block=resume_block,
            session_skills_block=session_skills,
            plan_open_block=plan_open,
            turn_state_block=turn_state_block,
            turn_bridge_block=bridge_block,
            peer_block=peer_block,
            envelope_follow_up_block=envelope_block,
            agent_tool_rules_block=tool_rules,
            recent_messages=_recent_message_dicts(recent_msgs),
            self_agent=agent,
        )
        manifest = build_manifest_via_recipe(activity, inputs)
    except Exception as exc:  # never let shadow instrumentation break the live turn
        return {"ok": False, "activity_phase": phase, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "ok": True,
        "activity": activity.value,
        "included_count": len(manifest.included),
        "excluded_count": len(manifest.excluded),
        "unresolved_count": len(manifest.unresolved_conflicts),
        "recipe_total_tokens": manifest.total_tokens,
        "legacy_total_chars": len(legacy_bundle.render()),
        "included_sources": sorted({item.source.value for item in manifest.included}),
    }
