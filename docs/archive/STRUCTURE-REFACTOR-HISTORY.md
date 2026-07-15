# Package structure refactor — consolidated history (all shipped)

> **Authority:** none — historical record of completed `src/agent_lab/*_*.py` → `src/agent_lab/<package>/` moves.
> Current LOC/import ratchets live in [`../STRUCTURE-METRICS.md`](../STRUCTURE-METRICS.md); active refactor waves
> (not yet closed) live in [`../STRUCTURE-REFACTOR-WAVE.md`](../STRUCTURE-REFACTOR-WAVE.md). This file replaces
> 13 near-identical per-package docs (`AGENT-`, `CONTEXT-`, `INBOX-`, `KIMI-`, `MISSION-`, `PLAN-`, `QUANT-`,
> `RESEARCH-`, `ROOM-`, `RUN-`, `SESSION-`, `WISDOM-`, `WORKSPACE-PACKAGE-REFACTOR-DESIGN.md`), consolidated
> 2026-07-15 to cut doc count — each was "(shipped)" with no open items.

## Room

**Status:** Shipped — facade = `src/agent_lab/room/__init__.py`; root `room.py` and all `room_*.py` shims removed.

28 `room_*.py` modules moved to `src/agent_lab/room/` (22 dedicated `tests/test_room_*.py` files). Facade uses
lazy exports in `room/__init__.py` so submodule imports (e.g. `agent_lab.room.sse_stream`) don't pull the full
orchestration graph.

Layer model (from the import graph):

```mermaid
flowchart TB
  subgraph facade["Facade"]
    room["room.py"]
  end
  subgraph orchestration["Orchestration"]
    turn_flow["room_turn_flow"]
    turn_meta["room_turn_meta"]
    parallel["room_parallel_rounds"]
    consensus_r["room_consensus_rounds"]
    session_p["room_session_persist"]
  end
  subgraph invoke["Agent invoke / stream"]
    invoke["room_agent_invoke"]
    sse["room_sse_stream"]
    dispatch["room_dispatch"]
    delegate["room_delegate"]
  end
  subgraph domain["Domain state"]
    messages["room_messages"]
    context["room_context"]
    consensus["room_consensus"]
    turn_state["room_turn_state"]
    tasks["room_tasks"]
    objections["room_objections"]
    mailbox["room_mailbox"]
    artifacts["room_artifacts"]
  end
  subgraph policy["Policy / hooks"]
    hooks["room_hooks"]
    preset["room_preset"]
    capabilities["room_agent_capabilities"]
    team["room_team_orchestration"]
  end
  subgraph leaf["Leaf / auxiliary"]
    plan_scribe["room_plan_scribe"]
    scribe_enrich["room_scribe_enrichment"]
    retry["room_retry"]
    live_log["room_live_log"]
    chat_ch["room_chat_channels"]
    dispatch_i["room_dispatch_intents"]
    models_cfg["room_models_config"]
  end

  room --> orchestration
  room --> invoke
  orchestration --> invoke
  orchestration --> domain
  orchestration --> policy
  invoke --> domain
  invoke --> policy
  domain --> leaf
  policy --> domain
```

Hub modules (≥5 outgoing in-package edges): `room_session_persist` (17, harvest pipeline), `room_consensus_rounds`
(13, consensus FSM), `room_turn_flow` (13, `run_room`/`continue_room_round` entry), `room_agent_invoke` (12, agent
call + SSE), `room_turn_meta` (8, plan sync/scribe triggers), `room_plan_scribe` (7), `room_parallel_rounds` (6),
`room_tasks` (5).

**Known structural issue (still relevant):** `room_dispatch.py` lazy-imports the facade
(`from agent_lab.room import ChatMessage, _call_one_agent, _session_context`), creating a
`room_dispatch → room → … → room_turn_meta → room_dispatch` cycle risk, currently broken only by lazy imports
inside functions. Detect regressions: `python scripts/room_import_graph.py --strict` (enforced in
`tests/test_structure_metrics.py`).

Facade surface (`agent_lab.room`, `room.py` `__all__`): turn drivers (`run_room`, `continue_room_round`,
`run_agent_rounds`, `run_consensus_agent_rounds`, `run_parallel_round`), session I/O (`load_session_messages`,
`save_room_session`, `room_session_context`), plan/scribe (`synthesize_plan`, `synthesize_session_plan`,
`ensure_*_plan_*`, `maybe_auto_scribe_*`), types/constants (`ChatMessage`, `AgentId`, `PLAN_FORMAT_VERSION`,
parallel round limits), plus internal names exported for tests/deps (`_session_context`, `_call_one_agent`,
`_delegate_run_meta_patch`, …). Guard: `make audit-room-imports` /
`tests/test_structure_metrics.py::test_audit_room_legacy_imports_passes`.

## Plan

**Status:** Shipped — mirrors the Room precedent, no root shims (direct 89-file rewrite).

20 `plan_*.py` modules (15+ dedicated `tests/test_plan_*.py` files) moved to `src/agent_lab/plan/` — no facade
(`plan/` package only, no `plan.py` namespace conflict).

| Old path | New path |
|----------|----------|
| `plan_actions.py` | `plan/actions.py` |
| `plan_advance.py` | `plan/advance.py` |
| `plan_execute.py` | `plan/execute.py` |
| `plan_execute_*` | `plan/execute_*` |
| `plan_paths.py` | `plan/paths.py` |
| `plan_peer_iterate.py` | `plan/peer_iterate.py` |
| `plan_peer_seats.py` | `plan/peer_seats.py` |
| `plan_pending.py` | `plan/pending.py` |
| `plan_provenance.py` | `plan/provenance.py` |
| `plan_refs.py` | `plan/refs.py` |
| `plan_sync_summary.py` | `plan/sync_summary.py` |
| `plan_workflow.py` | `plan/workflow.py` |

Canonical imports: `agent_lab.plan.execute`, `agent_lab.plan.workflow`, etc. Migration script (one-shot, kept for
reference): `scripts/migrate_plan_package.py`. Guard: `make audit-plan-imports` /
`tests/test_structure_metrics.py::test_audit_plan_legacy_imports_passes`; mypy strict ratchet via
`make typecheck-plan-ratchet` (0/0).

## Agent

Moved `agent_*.py` → `src/agent_lab/agent/` (singular — distinct from `agents/` registry): `agent_roster.py` →
`agent/roster.py`, `agent_health.py` → `agent/health.py`, `agent_envelope.py` → `agent/envelope.py`,
`agent_permissions.py` → `agent/permissions.py`, etc. Canonical imports: `agent_lab.agent.roster`,
`agent_lab.agent.health`. Roster tests alias `from agent_lab.agent import roster as ar`. Guard:
`make audit-agent-imports`, `make typecheck-agent-ratchet`; one-shot migration script:
`scripts/migrate_agent_package.py`.

## Context

Moved `context_*.py` → `src/agent_lab/context/`: `context_bundle.py` → `context/bundle.py`, `context_limits.py`
→ `context/limits.py`, `context_layers.py` → `context/layers.py`, `context_meta.py` → `context/meta.py`. Note:
`room/context/` (Wave B — constraints/peer_digest/plan_excerpt/message_trim) is a separate package; repo tree
stays in `repo_tree_context.py`. Guard: `make audit-context-imports`, `make typecheck-context-ratchet`.

## Inbox

Moved `inbox_*.py` → `src/agent_lab/inbox/` (Human gate harvest + MCP): `inbox_harvest.py` → `inbox/harvest.py`,
`inbox_facilitator.py` → `inbox/facilitator.py`, `inbox_mcp_policy.py` → `inbox/mcp_policy.py`,
`inbox_mcp_server.py` → `inbox/mcp_server.py`. MCP module path: `python -m agent_lab.inbox.mcp_server`. Cursor
bridge wiring stays at `cursor_inbox_mcp.py` (adapter layer). Guard: `make audit-inbox-imports`,
`make typecheck-inbox-ratchet`.

## Kimi

Moved `kimi_*.py` → `src/agent_lab/kimi/`: `kimi_provider.py` → `kimi/provider.py`, `kimi_control_client.py` →
`kimi/control_client.py`, `kimi_daimon_supervisor.py` → `kimi/daimon_supervisor.py`, `kimi_work_*.py` →
`kimi/work_*.py`. Registry wiring: `from agent_lab.kimi import provider as kimi_provider, work_provider as
kimi_work_provider`. Guard: `make audit-kimi-imports`; one-shot migration script:
`scripts/migrate_kimi_package.py`.

## Mission

Moved `mission_*.py` → `src/agent_lab/mission/`: `mission_loop.py` → `mission/loop.py`, `mission_advance.py` →
`mission/advance.py`, `mission_board.py` → `mission/board.py`, `mission_notepad.py` → `mission/notepad.py`,
`mission_scheduler.py` → `mission/scheduler.py`, `mission_templates.py` → `mission/templates.py`,
`mission_tick.py` → `mission/tick.py`. `trading_mission/` is a separate subpackage (quant lane, unchanged).
Guard: `make audit-mission-imports`; one-shot migration script: `scripts/migrate_mission_package.py`.

## Quant

Moved `quant_*.py` → `src/agent_lab/quant/` (trading lane utility validation): `quant_utility_validation.py` →
`quant/utility_validation.py`. Related subpackage `trading_mission/` unchanged. Guard: `make audit-quant-imports`,
`make typecheck-quant-ratchet`.

## Research

Moved `research_*.py` → `src/agent_lab/research/`: `research_artifact_card.py` → `research/artifact_card.py`,
`research_mcp_read.py` → `research/mcp_read.py`, `research_mcp_server.py` → `research/mcp_server.py`. MCP module
path: `python -m agent_lab.research.mcp_server`. Pipeline read helpers (`pipeline_research_read.py`,
`pipeline_market_read.py`) stayed at root — separate wave. Guard: `make audit-research-imports`,
`make typecheck-research-ratchet`.

## Run

Moved `run_*.py` → `src/agent_lab/run/` (`run.json` SSOT): `run_meta.py` → `run/meta.py`, `run_schema.py` →
`run/schema.py`, `run_control.py` → `run/control.py`, `run_profile.py` → `run/profile.py`,
`run_observability.py` → `run/observability.py`. `runner.py` (graph step runner) stayed at root — different
concern. Canonical helpers `patch_run_meta()` / `read_run_meta()` / `write_run_meta()` → `agent_lab.run.meta`.
Guard: `make audit-run-imports`, `make typecheck-run-ratchet`.

## Session

Moved `session.py` + `session_*.py` → `src/agent_lab/session/`: `session.py` → `session/__init__.py` (slugify,
session_dir, save_session + paths re-exports), `session_paths.py` → `session/paths.py`, `session_guidance.py` →
`session/guidance.py`, `session_clarifier.py` → `session/clarifier.py`, `session_setup.py` → `session/setup.py`,
`session_score.py` → `session/score.py`, `session_score_weekly.py` → `session/score_weekly.py`,
`session_plugin_runtime.py` → `session/plugin_runtime.py`. Guard: `make audit-session-imports`; one-shot
migration script: `scripts/migrate_session_package.py`.

## Wisdom

Moved `wisdom_*.py` → `src/agent_lab/wisdom/`: `wisdom_index.py` → `wisdom/index.py`, `wisdom_store.py` →
`wisdom/store.py`, `wisdom_mcp.py` → `wisdom/mcp.py`, `wisdom_mcp_server.py` → `wisdom/mcp_server.py`. MCP module
path: `python -m agent_lab.wisdom.mcp_server`. Guard: `make audit-wisdom-imports`,
`make typecheck-wisdom-ratchet`.

## Workspace

Moved `workspace_*.py` → `src/agent_lab/workspace/`: `workspace_roots.py` → `workspace/roots.py`,
`workspace_files.py` → `workspace/files.py`, `workspace_md.py` → `workspace/md.py`. API router
`app/server/routers/workspace_files.py` unchanged (HTTP layer). Guard: `make audit-workspace-imports`,
`make typecheck-workspace-ratchet`.
