"""CX1 producer → CX3 ContextItem adapter (09-context-engineering.md §11 CX1/CX8).

`context/recipe.py::select_context()` is a pure selector over already-built
`ContextItem`s; until this module, nothing produced them — every real source
was concatenated straight into a string by `context/bundle.py` (the legacy
assembler), completely bypassing `select_context()`. This module is the
missing link: one pure function per producer identified in
docs/redesign-2026-07/evidence/cx1-source-registry-2026-07-16.md §1, each
converting that producer's ALREADY-COMPUTED raw output (a plain string,
list[dict], or list[dataclass] — whatever the producer already returns) into
one or more `ContextItem`s.

Deliberate design choices:

- **Adapters take raw output, not the producer's inputs.** An adapter never
  reaches into the filesystem, `run_meta`, or calls a producer function
  itself. This keeps the module a pure, dependency-light transform (easy to
  test with synthetic data, no I/O to mock) and sidesteps re-implementing
  each producer's own gating/caching/side-effect logic (several producers —
  `steer.py::drain_steer_follow_up` in particular — are side-effecting or
  have caching semantics that don't belong duplicated here). Callers own
  invoking the real producer and passing its result in.

- **One adapter per producer, not one per SourceClass.** The CX1 registry's
  own §2 findings (AGENTS.md flat vs hierarchy; wisdom's 4-way notepad/
  index/store/playbook split) explicitly leave open whether/how multiple
  producers feeding the same SourceClass should be deduplicated or weighted
  against each other — that's a CX2/CX8 selection-composition decision for
  whoever wires a `ContextNeed` to real producers, not this module's job.

- **PROJECT.md's bootstrap (`project_memory.py::bootstrap_project_md`) and
  injection (`session/guidance.py`'s read path) registry rows collapse into
  one `adapt_project_md` adapter** — per the registry's own §2 ruling, they
  are producer/consumer of the same file, not two distinct content sources.

- **No adapter for `context/bundle.py::_format_grounding_block`.** It is not
  an independent producer: it's a conditional re-combination of the clarify-
  facts and goal-ledger content already covered by `adapt_clarify_facts`/
  `adapt_goal_ledger` (see `_format_grounding_block`'s own docstring — it
  calls `_format_clarity_facts` directly). Adapting it as a *third* item
  would double-count the same facts under a different item_id whenever
  anti-drift mode is off (the common case), since its rendered text is then
  byte-identical to the facts block. Compose grounding from
  `adapt_clarify_facts` + `adapt_goal_ledger` instead.

- **`agent_opinion` has no adapter.** The CX1 registry's §3 explicitly flags
  this as unresolved — no producer in `bundle.py` or elsewhere currently
  emits a structured "peer agent opinion" object (the closest candidate,
  raw peer chat messages via `room/context.py::format_peer_block`, is
  unstructured message text, not an opinion/analysis object). Confirm the
  producer before adapting it.

- **The registry doc's own header says "17 producers" but §1's table has 15
  rows** — this module adapts exactly those 15 rows (14 adapter functions,
  since PROJECT.md's two rows collapse into one and grounding isn't
  independent). This is a pre-existing miscount in the CX1 doc, not
  something this module resolves by inventing two more producers.

- **`trusted`/`security_label` are left at `ContextItem`'s defaults** for
  every adapter here: the CX1 registry's §4 acceptance-criteria table notes
  all current producers are internal, system-produced, non-secret content
  (`trusted=True` via the default posture, `security_label="project"`).
  None of these 15 producers surface external/tool content (that's CX6/
  `SourceClass.EXTERNAL_CONTENT` territory) or secret/credential/pii data.

- **`authority` values** are integers on a 0-100 scale derived from the
  registry's own qualitative column: 최상(top)=100, 높음(high)=80,
  중상(medium-high)=60, 중(medium)=40. These are first-draft numbers, same
  status as the rest of CX1-CX4 — still Human-review pending, not
  calibrated against real selection outcomes.
"""

from __future__ import annotations

from typing import Any

from agent_lab.context.recipe import ContextItem, SourceClass, estimate_tokens
from agent_lab.wisdom.playbook import PlaybookBullet
from agent_lab.wisdom.store import WisdomEntry

AUTHORITY_TOP = 100
AUTHORITY_HIGH = 80
AUTHORITY_MEDIUM_HIGH = 60
AUTHORITY_MEDIUM = 40


def adapt_project_md(content: str, *, mtime: float | None = None) -> ContextItem | None:
    """`project_memory.py::bootstrap_project_md` (write) + `session/
    guidance.py`'s PROJECT.md read (injection) — registry rows 1-2,
    collapsed per CX1 §2 (producer/consumer of the same file)."""
    if not content.strip():
        return None
    return ContextItem(
        item_id="project_md",
        source=SourceClass.PROJECT_DOC,
        content=content,
        authority=AUTHORITY_MEDIUM_HIGH,
        relevance=AUTHORITY_MEDIUM_HIGH,
        estimated_tokens=estimate_tokens(content),
        provenance=".agent-lab/PROJECT.md",
        freshness=str(mtime) if mtime is not None else None,
    )


def adapt_agents_md_flat(content: str, *, mtime: float | None = None) -> ContextItem | None:
    """`workspace/md.py::read_agents_md_for_injection` — workspace-root
    AGENTS.md, flat (registry row 3)."""
    if not content.strip():
        return None
    return ContextItem(
        item_id="agents_md_flat",
        source=SourceClass.PROJECT_DOC,
        content=content,
        authority=AUTHORITY_MEDIUM_HIGH,
        relevance=AUTHORITY_MEDIUM_HIGH,
        estimated_tokens=estimate_tokens(content),
        provenance="AGENTS.md",
        freshness=str(mtime) if mtime is not None else None,
    )


def adapt_agents_md_hierarchy(content: str) -> ContextItem | None:
    """`workspace/md.py::read_agents_md_hierarchy_for_injection` — ancestor-
    chain AGENTS.md from plan path hints (registry row 4). Deliberately no
    shared conflict_key with `adapt_agents_md_flat`: CX1 §2 explicitly left
    open whether flat/hierarchy should compete for one slot or coexist, so
    this adapter doesn't force that decision."""
    if not content.strip():
        return None
    return ContextItem(
        item_id="agents_md_hierarchy",
        source=SourceClass.PROJECT_DOC,
        content=content,
        authority=AUTHORITY_MEDIUM_HIGH,
        relevance=AUTHORITY_MEDIUM_HIGH,
        estimated_tokens=estimate_tokens(content),
        provenance="AGENTS.md (per-dir hierarchy)",
    )


def adapt_shared_context_md(content: str) -> ContextItem | None:
    """`workspace/md.py::read_shared_context_for_injection` — workspace-root
    SHARED_CONTEXT.md (registry row 5)."""
    if not content.strip():
        return None
    return ContextItem(
        item_id="shared_context_md",
        source=SourceClass.PROJECT_DOC,
        content=content,
        authority=AUTHORITY_MEDIUM_HIGH,
        relevance=AUTHORITY_MEDIUM_HIGH,
        estimated_tokens=estimate_tokens(content),
        provenance="SHARED_CONTEXT.md",
    )


def adapt_repo_tree(content: str, *, commit_sha: str | None = None) -> ContextItem | None:
    """`repo_tree_context.py::build_repo_tree_block` — depth-limited repo
    file tree listing (registry row 6). `commit_sha` is optional because the
    producer itself doesn't currently capture one (a directory listing, not
    a git-aware snapshot) — pass it in when the caller has it."""
    if not content.strip():
        return None
    return ContextItem(
        item_id="repo_tree",
        source=SourceClass.REPO_CONTEXT,
        content=content,
        authority=AUTHORITY_MEDIUM_HIGH,
        relevance=AUTHORITY_MEDIUM_HIGH,
        estimated_tokens=estimate_tokens(content),
        provenance="repo tree listing",
        freshness=commit_sha,
    )


def adapt_session_guidance(content: str) -> ContextItem | None:
    """`session/guidance.py::build_session_guidance_block` — session phase/
    workspace-binding/steer guidance prose (registry row 7). Note: the real
    function's body also embeds PROJECT.md/AGENTS.md/SHARED_CONTEXT.md text
    via its own internal calls — if a caller ALSO includes
    adapt_project_md/adapt_agents_md_*/adapt_shared_context_md as separate
    items, there is intentional content overlap with this item (the registry
    maps the whole function to one HUMAN_INTENT row; decomposing it further
    is CX2/CX8 scope, not this adapter's)."""
    if not content.strip():
        return None
    return ContextItem(
        item_id="session_guidance",
        source=SourceClass.HUMAN_INTENT,
        content=content,
        authority=AUTHORITY_HIGH,
        relevance=AUTHORITY_HIGH,
        estimated_tokens=estimate_tokens(content),
        provenance="session/guidance.py::build_session_guidance_block",
    )


def adapt_approved_plan(plan_md: str) -> ContextItem | None:
    """`plan_md` — not one of CX1's original 15 registry rows (the registry
    only cataloged what `bundle.py` itself produces internally), but every
    `build_context_bundle`/`build_slim_consensus_bundle` call site already
    receives `plan_md: str` as a parameter, and it's the only readily
    available source for `SourceClass.APPROVED_PLAN` — a source every
    activity recipe except CLARIFY requires (`activity_recipes.py`) but
    that CX1's registry never identified a producer for. Added while wiring
    the CX8 convergence slice (2026-07-16)."""
    if not plan_md.strip():
        return None
    return ContextItem(
        item_id="approved_plan",
        source=SourceClass.APPROVED_PLAN,
        content=plan_md,
        authority=AUTHORITY_TOP,
        relevance=AUTHORITY_TOP,
        estimated_tokens=estimate_tokens(plan_md),
        provenance="plan.md",
    )


def adapt_reply_policy_guidance(parts: list[str]) -> list[ContextItem]:
    """`reply_policy.py::build_guidance_parts` — response-contract/dispatch-
    lead/persona/coordination guidance (registry row 8). Already a
    `list[str]`, the best-shaped producer for item-per-part."""
    items: list[ContextItem] = []
    for index, part in enumerate(parts):
        if not part.strip():
            continue
        items.append(
            ContextItem(
                item_id=f"guidance_part:{index}",
                source=SourceClass.SYSTEM_INVARIANT,
                content=part,
                authority=AUTHORITY_TOP,
                relevance=AUTHORITY_TOP,
                estimated_tokens=estimate_tokens(part),
                provenance="reply_policy.py::build_guidance_parts",
            )
        )
    return items


def adapt_mission_notepad(content: str, *, session_id: str = "") -> ContextItem | None:
    """`mission/notepad.py::build_mission_wisdom_block` — session-scoped
    mission notepad tail (registry row 9)."""
    if not content.strip():
        return None
    return ContextItem(
        item_id=f"mission_notepad:{session_id}" if session_id else "mission_notepad",
        source=SourceClass.EPISODE,
        content=content,
        authority=AUTHORITY_MEDIUM,
        relevance=AUTHORITY_MEDIUM,
        estimated_tokens=estimate_tokens(content),
        provenance="mission/notepad.py",
    )


def _adapt_single_block(
    content: str,
    *,
    item_id: str,
    source: SourceClass,
    authority: int,
    provenance: str,
) -> ContextItem | None:
    """Shared shape for the several bundle.py producers that already
    return ONE fully-rendered string block with no further structure to
    preserve (team task board, objections, plugin allowlist, turn state,
    etc.) — mirrors adapt_session_guidance/adapt_repo_tree's pattern rather
    than repeating the same six-line ContextItem construction at every call
    site below."""
    if not content.strip():
        return None
    return ContextItem(
        item_id=item_id,
        source=source,
        content=content,
        authority=authority,
        relevance=authority,
        estimated_tokens=estimate_tokens(content),
        provenance=provenance,
    )


def adapt_team_task_block(content: str) -> ContextItem | None:
    """`room/tasks.py::build_team_task_block` — the current team task
    board (owner/status per task, claimable items)."""
    return _adapt_single_block(
        content,
        item_id="team_task_block",
        source=SourceClass.RUNTIME_STATE,
        authority=AUTHORITY_HIGH,
        provenance="room/tasks.py::build_team_task_block",
    )


def adapt_objection_block(content: str) -> ContextItem | None:
    """`room/objections.py::build_objection_block` — unresolved BLOCK/
    CHALLENGE objections from peers, needing Human or AMEND resolution."""
    return _adapt_single_block(
        content,
        item_id="objection_block",
        source=SourceClass.RUNTIME_STATE,
        authority=AUTHORITY_HIGH,
        provenance="room/objections.py::build_objection_block",
    )


def adapt_challenge_owner_block(content: str) -> ContextItem | None:
    """`room/objections.py::build_challenge_owner_block` — E3: the task
    owner must AMEND or justify while a CHALLENGE against their task is open."""
    return _adapt_single_block(
        content,
        item_id="challenge_owner_block",
        source=SourceClass.RUNTIME_STATE,
        authority=AUTHORITY_HIGH,
        provenance="room/objections.py::build_challenge_owner_block",
    )


def adapt_plugin_allowlist_block(content: str) -> ContextItem | None:
    """`plugin_discovery.py::build_plugin_allowlist_block` — which plugins/
    MCP/skills Human enabled for this agent this session (a tool-grant
    boundary, hence SYSTEM_INVARIANT rather than RUNTIME_STATE)."""
    return _adapt_single_block(
        content,
        item_id="plugin_allowlist_block",
        source=SourceClass.SYSTEM_INVARIANT,
        authority=AUTHORITY_TOP,
        provenance="plugin_discovery.py::build_plugin_allowlist_block",
    )


def adapt_capability_preamble(content: str) -> ContextItem | None:
    """`room/agent_capabilities.py::capability_preamble_block` — what tools/
    capabilities this agent has this round (another tool-grant boundary)."""
    return _adapt_single_block(
        content,
        item_id="capability_preamble",
        source=SourceClass.SYSTEM_INVARIANT,
        authority=AUTHORITY_TOP,
        provenance="room/agent_capabilities.py::capability_preamble_block",
    )


def adapt_thread_resume_block(content: str) -> ContextItem | None:
    """`agent/thread_resume.py::build_agent_thread_resume_block` — prior-
    session continuity context when this agent's thread was rebound."""
    return _adapt_single_block(
        content,
        item_id="thread_resume_block",
        source=SourceClass.RUNTIME_STATE,
        authority=AUTHORITY_MEDIUM_HIGH,
        provenance="agent/thread_resume.py::build_agent_thread_resume_block",
    )


def adapt_session_skills_block(content: str) -> ContextItem | None:
    """`skill_drafts.py::build_session_skills_block` — skills learned
    during THIS mission (its own header literally says "learned this
    mission"), hence EPISODE rather than the longer-lived SEMANTIC_MEMORY
    playbook/wisdom-index sources."""
    return _adapt_single_block(
        content,
        item_id="session_skills_block",
        source=SourceClass.EPISODE,
        authority=AUTHORITY_MEDIUM,
        provenance="skill_drafts.py::build_session_skills_block",
    )


def adapt_dispatch_intent_block(content: str) -> ContextItem | None:
    """`room/dispatch_intents.py::build_dispatch_intent_block` — pending
    DELEGATE/DISPATCH intents targeting this agent or issued by the lead."""
    return _adapt_single_block(
        content,
        item_id="dispatch_intent_block",
        source=SourceClass.RUNTIME_STATE,
        authority=AUTHORITY_HIGH,
        provenance="room/dispatch_intents.py::build_dispatch_intent_block",
    )


def adapt_plan_open_block(content: str) -> ContextItem | None:
    """`room/context/plan_excerpt.py::build_plan_open_block` — plan.md's
    open/unresolved bullets. Distinct from `SourceClass.APPROVED_PLAN`
    (`adapt_approved_plan`): these are explicitly NOT-yet-resolved items,
    not the confirmed plan itself."""
    return _adapt_single_block(
        content,
        item_id="plan_open_block",
        source=SourceClass.RUNTIME_STATE,
        authority=AUTHORITY_HIGH,
        provenance="room/context/plan_excerpt.py::build_plan_open_block",
    )


def adapt_turn_state_block(content: str) -> ContextItem | None:
    """`room/turn_state.py::render_turn_state_block` — the structured
    turn-state blackboard (anchor, open issues, decisions, pending agents)."""
    return _adapt_single_block(
        content,
        item_id="turn_state_block",
        source=SourceClass.RUNTIME_STATE,
        authority=AUTHORITY_HIGH,
        provenance="room/turn_state.py::render_turn_state_block",
    )


def adapt_turn_bridge_block(content: str) -> ContextItem | None:
    """`room/context/peer_digest.py::build_turn_bridge_block` — an R1
    summary of peer replies before round 2+ (AGENT_LAB_R15). This and
    `adapt_peer_block` are peer AGENTS' own words, not this system's own
    facts, hence AGENT_OPINION — the same taxonomy slot CX1 §3 flagged as
    having no confirmed producer; peer chat content is the closest fit."""
    return _adapt_single_block(
        content,
        item_id="turn_bridge_block",
        source=SourceClass.AGENT_OPINION,
        authority=AUTHORITY_MEDIUM,
        provenance="room/context/peer_digest.py::build_turn_bridge_block",
    )


def adapt_peer_block(content: str) -> ContextItem | None:
    """`room/context/peer_digest.py::format_peer_block` — this turn's peer
    agent messages. See `adapt_turn_bridge_block` re: AGENT_OPINION mapping."""
    return _adapt_single_block(
        content,
        item_id="peer_block",
        source=SourceClass.AGENT_OPINION,
        authority=AUTHORITY_MEDIUM,
        provenance="room/context/peer_digest.py::format_peer_block",
    )


def adapt_envelope_follow_up_block(content: str) -> ContextItem | None:
    """`reply_policy.py::envelope_follow_up_block` — envelope-format
    follow-up instructions for this turn (a procedural rule, hence
    SYSTEM_INVARIANT rather than RUNTIME_STATE)."""
    return _adapt_single_block(
        content,
        item_id="envelope_follow_up_block",
        source=SourceClass.SYSTEM_INVARIANT,
        authority=AUTHORITY_TOP,
        provenance="reply_policy.py::envelope_follow_up_block",
    )


def adapt_agent_tool_rules_block(content: str) -> ContextItem | None:
    """`room/context/constraints.py::agent_tool_rules` — which tools this
    agent may use and under what rules this turn."""
    return _adapt_single_block(
        content,
        item_id="agent_tool_rules_block",
        source=SourceClass.SYSTEM_INVARIANT,
        authority=AUTHORITY_TOP,
        provenance="room/context/constraints.py::agent_tool_rules",
    )


def adapt_mailbox_messages(rows: list[dict[str, Any]]) -> list[ContextItem]:
    """`room/mailbox.py::unread_for_agent` — unread direct messages FROM
    peer agents TO this agent. Takes the read-only `unread_for_agent`
    output, not `build_mailbox_block` itself: that function has a side
    effect (`mark_delivered`, marking messages read once rendered), which
    this module's "never mutate, take already-computed output" rule
    excludes — a caller that wants delivery marked owns calling
    `mark_delivered` itself, separately from adapting.

    Maps to AGENT_OPINION: a peer agent's direct message is that peer's own
    communication, the same taxonomy slot `adapt_turn_bridge_block`/
    `adapt_peer_block` use and that CX1 §3 flagged as lacking a confirmed
    producer."""
    items: list[ContextItem] = []
    for row in rows:
        message_id = str(row.get("id") or "").strip()
        body = str(row.get("body") or "").strip()
        if not message_id or not body:
            continue
        sender = str(row.get("from") or "").strip()
        content = f"{sender}: {body}" if sender else body
        items.append(
            ContextItem(
                item_id=f"mailbox:{message_id}",
                source=SourceClass.AGENT_OPINION,
                content=content,
                authority=AUTHORITY_MEDIUM,
                relevance=AUTHORITY_MEDIUM,
                estimated_tokens=estimate_tokens(content),
                provenance="room/mailbox.py",
                freshness=str(row.get("ts")) if row.get("ts") else None,
            )
        )
    return items


def adapt_recent_messages(rows: list[dict[str, Any]], *, self_agent: str = "") -> list[ContextItem]:
    """`room/context/message_trim.py::build_recent_turns_block`/
    `prepare_recent_messages` — the recent Human+agent conversation turns
    (`ChatMessage.to_dict()`'s shape: `{role: "user"|"agent"|"system",
    agent, content, ts, parallel_round?}`), previously left unadapted (see
    `context/bundle_recipe.py`'s module docstring) as a genuine taxonomy
    gap: no single `SourceClass` cleanly captures "the ongoing conversation."

    2026-07-16 — resolved by decomposing PER MESSAGE, keyed on `role` (and
    `agent` for role="agent"), rather than treating the transcript as one
    opaque blob — the same "structured list, not a rendered string" pattern
    `adapt_clarify_facts`/`adapt_goal_ledger`/`adapt_artifacts` already use:

    - `role == "user"` (what the Human said) -> HUMAN_INTENT. This is
      exactly what 09-context-engineering.md §12's "현재 Human intent"
      refers to — the Human's own recent turns are its primary vehicle.
    - `role == "agent"` and `agent == self_agent` (this agent's own prior
      replies this session) -> EPISODE. Distinct from a PEER's opinion —
      this is the agent's own session-scoped history, not another agent's
      analysis.
    - `role == "agent"` and `agent != self_agent` (a peer message that
      wasn't filtered out of `messages` before reaching this adapter) ->
      AGENT_OPINION, same slot as `adapt_mailbox_messages`/`adapt_peer_
      block`. Callers that already dedupe peer lines into a separate
      `peer_msgs` list (as `dedupe_peer_from_recent` does today) won't hit
      this branch at all; it exists so a caller that DOESN'T dedupe first
      still gets a defensible mapping instead of silently mis-tagging peer
      content as this agent's own EPISODE.
    - `role == "system"` (ephemeral system-injected notices) -> RUNTIME_STATE,
      the same generic "current turn/session state" bucket the other
      recently-added adapters use.

    item_id is index-based (`f"recent:{index}"`) like `adapt_goal_ledger` —
    chat.jsonl rows carry a `ts` but no stable per-message id, and two
    messages can share a `ts` (near-simultaneous parallel replies), so an
    index is the only thing guaranteed unique here; it is NOT stable across
    edits to the message list, same caveat as goal_ledger."""
    items: list[ContextItem] = []
    self_agent_l = self_agent.strip().lower()
    for index, row in enumerate(rows):
        content = str(row.get("content") or "").strip()
        role = str(row.get("role") or "").strip()
        if not content or role not in ("user", "agent", "system"):
            continue
        agent = str(row.get("agent") or "").strip().lower()
        if role == "user":
            source = SourceClass.HUMAN_INTENT
            authority = AUTHORITY_HIGH
        elif role == "agent" and agent == self_agent_l and self_agent_l:
            source = SourceClass.EPISODE
            authority = AUTHORITY_MEDIUM
        elif role == "agent":
            source = SourceClass.AGENT_OPINION
            authority = AUTHORITY_MEDIUM
        else:
            source = SourceClass.RUNTIME_STATE
            authority = AUTHORITY_MEDIUM
        items.append(
            ContextItem(
                item_id=f"recent:{index}",
                source=source,
                content=content,
                authority=authority,
                relevance=authority,
                estimated_tokens=estimate_tokens(content),
                provenance="room/context/message_trim.py",
                freshness=str(row.get("ts")) if row.get("ts") else None,
            )
        )
    return items


def adapt_steer_queue(entries: list[dict[str, Any]]) -> list[ContextItem]:
    """`steer.py::list_steer_queue` (the already-drained/queued entries, NOT
    `drain_steer_follow_up` — that call is side-effecting/consuming, so this
    adapter takes the entry list a caller already has, rather than draining
    the queue itself) — registry row 10. Each entry: `{id, text, ts,
    target}` (see `steer.py::enqueue_steer`)."""
    items: list[ContextItem] = []
    for entry in entries:
        text = str(entry.get("text") or "").strip()
        entry_id = str(entry.get("id") or "").strip()
        if not text or not entry_id:
            continue
        items.append(
            ContextItem(
                item_id=f"steer:{entry_id}",
                source=SourceClass.HUMAN_INTENT,
                content=text,
                authority=AUTHORITY_HIGH,
                relevance=AUTHORITY_HIGH,
                estimated_tokens=estimate_tokens(text),
                provenance="steer.py (Human steer queue)",
                freshness=str(entry.get("ts")) if entry.get("ts") else None,
            )
        )
    return items


def adapt_wisdom_index_hits(hits: list[dict[str, Any]]) -> list[ContextItem]:
    """`wisdom/index.py::search_wisdom_index` — cross-session wisdom index
    search hits (registry row 11). Each hit already carries a `score`
    (0..~few) — used directly as `relevance`, rounded to an int; the
    producer already sorts by it, so this preserves its ranking signal
    instead of inventing a new one."""
    items: list[ContextItem] = []
    for hit in hits:
        hit_id = str(hit.get("id") or "").strip()
        snippet = str(hit.get("snippet") or "").strip()
        if not hit_id or not snippet:
            continue
        items.append(
            ContextItem(
                item_id=f"wisdom_index:{hit_id}",
                source=SourceClass.SEMANTIC_MEMORY,
                content=snippet,
                authority=AUTHORITY_MEDIUM_HIGH,
                relevance=max(1, round(float(hit.get("score") or 0))),
                estimated_tokens=estimate_tokens(snippet),
                provenance=str(hit.get("path") or hit.get("source") or "wisdom/index.py"),
                freshness=str(hit.get("at")) if hit.get("at") else None,
            )
        )
    return items


def adapt_artifacts(rows: list[dict[str, Any]]) -> list[ContextItem]:
    """`room/artifacts.py::recent_artifacts_for_agent`/`list_artifacts` — Room
    agents' recorded work product (diffs/tables/logs/file refs), the closest
    existing producer to `SourceClass.EVIDENCE`. CX1's registry never
    catalogued this producer (it lives under `room/`, not `context/`), and no
    adapter existed for EVIDENCE until this one — added specifically to
    unblock CRITIC/REPAIR/SCRIBE recipes, which all require EVIDENCE
    (`activity_recipes.py`) but could never previously build a manifest
    through `context/bundle_recipe.py::build_manifest_via_recipe`.

    Each row (`room/artifacts.py::normalize_artifact`'s shape: `{id,
    producer, kind, summary, ts, path?, turn?, refs?, parallel_round?}`) maps
    its `summary` field to content — NOT the full artifact body some rows
    persist to disk at `path` (`room/artifacts.py::_read_artifact_body`
    reads that separately, with its own truncation/session-folder
    resolution). Reading that body here would violate this module's "take
    already-computed output, never touch the filesystem" rule; a caller
    with the body already loaded can pass a pre-expanded `summary` instead."""
    items: list[ContextItem] = []
    for row in rows:
        artifact_id = str(row.get("id") or "").strip()
        summary = str(row.get("summary") or "").strip()
        if not artifact_id or not summary:
            continue
        items.append(
            ContextItem(
                item_id=f"artifact:{artifact_id}",
                source=SourceClass.EVIDENCE,
                content=summary,
                authority=AUTHORITY_HIGH,
                relevance=AUTHORITY_HIGH,
                estimated_tokens=estimate_tokens(summary),
                provenance=str(row.get("path") or "room/artifacts.py"),
                freshness=str(row.get("ts")) if row.get("ts") else None,
            )
        )
    return items


def adapt_playbook_bullets(bullets: list[PlaybookBullet]) -> list[ContextItem]:
    """`wisdom/playbook.py::playbook_bullets_for_topic` — approved playbook
    bullets, already ranked/top-k'd by the producer (registry row 12)."""
    items: list[ContextItem] = []
    for bullet in bullets:
        content = bullet.description.strip()
        if not bullet.id or not content:
            continue
        items.append(
            ContextItem(
                item_id=f"playbook:{bullet.id}",
                source=SourceClass.SEMANTIC_MEMORY,
                content=content,
                authority=AUTHORITY_MEDIUM_HIGH,
                relevance=AUTHORITY_MEDIUM_HIGH,
                estimated_tokens=estimate_tokens(content),
                provenance=f"wisdom/playbook.py (pattern={bullet.pattern_id}, harness_rev={bullet.harness_rev})",
                freshness=bullet.updated_at or None,
            )
        )
    return items


def adapt_wisdom_entries(entries: list[WisdomEntry]) -> list[ContextItem]:
    """`wisdom/store.py::wisdom_query`/`wisdom_list_recent` — append-only
    wisdom entry log (registry row 13)."""
    items: list[ContextItem] = []
    for entry in entries:
        content = entry.content.strip()
        if not entry.id or not content:
            continue
        items.append(
            ContextItem(
                item_id=f"wisdom_entry:{entry.id}",
                source=SourceClass.EPISODE,
                content=content,
                authority=AUTHORITY_MEDIUM,
                relevance=AUTHORITY_MEDIUM,
                estimated_tokens=estimate_tokens(content),
                provenance=entry.source_ref or "wisdom/store.py",
                freshness=entry.timestamp or None,
            )
        )
    return items


def adapt_clarify_facts(facts: list[dict[str, Any]]) -> list[ContextItem]:
    """`context/bundle.py::_format_clarity_facts` — confirmed CLARIFY facts
    from `run_meta.mission_loop.clarity.facts` (registry row 14). Reads the
    facts directly (via `clarity.py::established_facts`'s shape, `{id,
    category, component, question, answer, fact, at}`) rather than the
    pre-rendered string, so each fact becomes its own item instead of one
    merged block."""
    items: list[ContextItem] = []
    for fact in facts:
        fact_id = str(fact.get("id") or "").strip()
        answer = str(fact.get("answer") or fact.get("fact") or "").strip()
        if not fact_id or not answer:
            continue
        items.append(
            ContextItem(
                item_id=f"clarify_fact:{fact_id}",
                source=SourceClass.RUNTIME_STATE,
                content=answer,
                authority=AUTHORITY_HIGH,
                relevance=AUTHORITY_HIGH,
                estimated_tokens=estimate_tokens(answer),
                provenance="run_meta.mission_loop.clarity.facts",
                freshness=str(fact.get("at")) if fact.get("at") else None,
                conflict_key=f"clarify_fact:{fact_id}",
            )
        )
    return items


def adapt_goal_ledger(entries: list[dict[str, Any]]) -> list[ContextItem]:
    """`context/bundle.py::_format_decision_ledger` — recent goal-ledger
    decisions from `run_meta.goal_ledger` (registry row 15). Entries have no
    stable id or timestamp field today (just `event`/`phase`/`note`), so
    item_id is index-based — NOT stable across appends to the ledger (an
    entry's index shifts as new entries are added). Freshness is left unset
    for the same reason; callers relying on freshness-based tie-breaks for
    ledger items should not expect a meaningful signal here until the
    ledger-writing code (outside this module) starts stamping entries."""
    items: list[ContextItem] = []
    for index, entry in enumerate(entries):
        event = str(entry.get("event") or "").strip()
        if not event:
            continue
        phase = str(entry.get("phase") or "").strip()
        note = str(entry.get("note") or "").strip()
        suffix = " · ".join(part for part in (phase, note) if part)
        content = f"{event}{(' · ' + suffix) if suffix else ''}"
        items.append(
            ContextItem(
                item_id=f"goal_ledger:{index}",
                source=SourceClass.RUNTIME_STATE,
                content=content,
                authority=AUTHORITY_HIGH,
                relevance=AUTHORITY_HIGH,
                estimated_tokens=estimate_tokens(content),
                provenance="run_meta.goal_ledger",
            )
        )
    return items
