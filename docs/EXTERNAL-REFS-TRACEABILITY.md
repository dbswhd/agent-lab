# External refs plan — traceability matrix

Maps items in [`EXTERNAL-REFS-PLAN.md`](EXTERNAL-REFS-PLAN.md) to **shipped code**, **regression/smoke evidence**, or **future fixture tickets**.  
This document is the hub for **plan vs reality**. It does not explain *why* an item was adopted — see PLAN §anchor for that context.

**Status legend:** ✅ shipped · 🔶 partial · ⬜ future · ❌ dropped  
**Related:** [EXTERNAL-REFS-PLAN.md](EXTERNAL-REFS-PLAN.md) (why/what) · [MD-WRITING-PLAN.md](MD-WRITING-PLAN.md) (MD authoring guide)  
**Dev-tool cross-ref:** `CC-CLAUDE` is tracked in [§Dev-tool](#dev-tool--prompt-layer-md-writing-plan-items) only (not duplicated in the runtime table below).

---

## Shipped (evidence in repo)

| ID | Source | Item | Status | Evidence | Notes |
|----|--------|------|--------|----------|-------|
| L1 | LazyCodex | CLI retry loop | ✅ | `src/agent_lab/cli_retry.py`, `tests/test_cli_retry.py`, R-P0 | Layer 1 |
| L2 | LazyCodex | Consensus loop | ✅ | `src/agent_lab/room_consensus.py`, `room.py` | Layer 2, cap_rounds/calls |
| LC-oracle | LazyCodex | Oracle verified completion (mock-first) | ✅ | `plan_execute_merge.py:oracle_verify()`, `tests/test_oracle_verify.py`, `.env.example` `AGENT_LAB_ORACLE_LIVE` | Mock default; live Claude via `AGENT_LAB_ORACLE_LIVE=1` (no separate runbook — LC-L3 reverify covers repair loop) |
| LC-L3 | LazyCodex | Execute verify + agent repair loop | ✅ | `verify_after_merge()`, `oracle_verify()`, `src/agent_lab/plan_execute.py`, `/api/sessions/{id}/execute/reverify`, `PlanExecutePanel.tsx`, `sessions/_regression/execute_verify_loop/`, `tests/test_plan_execute_agent_repair.py` | Oracle FAIL opens a fresh Cursor/Codex worktree repair, re-merges, and re-verifies; `MAX_VERIFY_RETRIES=2` |
| PI | Conductor | Git worktree execute + merge | ✅ | `src/agent_lab/plan_execute_*.py`, `sessions/_regression/worktree_*`, `tests/test_plan_execute_worktree.py` | Phase I M0–M4 |
| CON-diff | Conductor | Diff hunk inline revise | ✅ | `PlanExecutePanel.tsx`, `revise_pending_execution()`, `tests/test_plan_execute_revise_api.py` | Human hunk comment → fresh worktree re-diff → re-approve |
| PI-executed | Conductor | Merged diff archive | ✅ | `plan_execute_merge.py:archive_executed_diff()`, `tests/test_executed_archive.py` | `sessions/<id>/executed/{exec_id}.json` |
| PI-ops | Conductor | Live worktree Go/No-Go | ✅ | `docs/LIVE-CURSOR-WORKTREE-DRY-RUN.md`, `scripts/live_cursor_worktree_dry_run.py`, Tier B in `docs/OPS-RUNBOOK.md` | Manual, not CI |
| PI-ops-C | Conductor | Live merge operator | ✅ | `docs/LIVE-MERGE-OPERATOR.md`, `scripts/live_cursor_worktree_merge_run.py`, `make verify-ops-live-merge` | Disposable repo only |
| E-smoke | Room | BLOCK/CHALLENGE governance | ✅ | `sessions/_regression/objection_blocks_execute/`, `challenge_revises_metric/`, `scripts/smoke_room.py` | 23 baselines |
| F-R3 | Room | Asymmetric `capability_cwd` | ✅ | `sessions/_benchmark/specialist_asymmetric_cwd/`, `tests/test_benchmark_catalog.py` | Payload meta |
| H-P1 | H4 | score_session CI | ✅ | `scripts/score_session.py`, `tests/test_session_score_ci.py`, `.github/workflows/ci.yml` | |
| H-P2 | Room | Benchmark catalog + delegate replay | ✅ | `sessions/_benchmark/`, `tests/test_benchmark_catalog.py`, `tests/test_room_delegate_replay.py` | Offline R1–R5 catalog; PLAN Phase 3; see [ROOM-REINFORCEMENT.md](ROOM-REINFORCEMENT.md) |
| H4-weekly | H4 | Weekly KPI + M4 gates | ✅ | `scripts/score_sessions_weekly.py`, `src/agent_lab/session_score_weekly.py` | |
| H4-ops | H4 | Weekly ops artifact | ✅ | `format_weekly_report_markdown`, `make score-weekly`, `sessions/_reports/` | gitignored artifacts |
| H4-ops-live | H4 | Last live check in weekly | ✅ | `discover_live_ops_reports`, `tests/test_weekly_live_ops_summary.py` | Tier B/C JSON scan |
| ops-P0 | Platform | FastAPI lifespan | ✅ | `app/server/main.py` lifespan | |
| ops-P2 | Platform | Router split | ✅ | `app/server/routers/*`, `app/server/main.py` | |
| ops-verify | Platform | Manual ops routine | ✅ | `make verify-ops`, `tests/test_verify_ops_makefile.py`, `docs/OPS-RUNBOOK.md` | Tier A |
| R-P0 | Room | Partial turn | ✅ | `src/agent_lab/room.py`, `docs/STABILITY.md` | |
| R-P1 | Room | F2 artifact-only R2 | ✅ | `sessions/_regression/specialist_r2_artifact_only/`, `context_bundle.py` | |
| HOOK-COMM | Hook · Communicate reform | ✅ | `reply_policy.py`, `room_hooks.py`, `gate_snapshot.py`, `communicate_kpis.py`, `structured_envelope_adapter.py`, `agent_hooks_materializer.py`, `run_observability.py`, `make verify-hooks`, `make measure-communicate-baseline`, USER-GUIDE §9.8 | Phase 5 complete except optional `LEGACY_ENDORSE=0` migration — [HOOK-COMMUNICATE-REFORM.md](./HOOK-COMMUNICATE-REFORM.md) |
| UX-P2 | Room | Objection resolve UX | ✅ | `PlanExecutePanel.tsx`, `RoomTaskBar.tsx` | |
| Bridge | Room | Cursor bridge degraded | ✅ | `sessions/_regression/bridge_degraded_health/`, H-P3 tests | |
| CENT-env | Centaur | Subprocess env allowlist | ✅ | `src/agent_lab/subprocess_env.py`, `claude_cli.py`, `codex_cli.py`, `cursor_bridge.py`, `tests/test_subprocess_env.py` | [PLAN §3.2](EXTERNAL-REFS-PLAN.md#32-subprocess-credential-분리) |
| LC-L4 | LazyCodex | Adversarial gate (mock + UI) | ✅ | `adversarial_gate.py`, `PlanExecutePanel.tsx`, `docs/LC-L4-ADVERSARIAL-LIVE.md`, `sessions/_regression/adversarial_gate_lgtm/` | Mock default; live opt-in in LC-L4 doc |
| LC-L5 | LazyCodex | Goal-driven session loop | ✅ | `goal_loop.py`, `RoomChat.tsx`, `docs/GOAL-LOOP.md`, `sessions/_regression/goal_loop_achieved/`, `tests/test_goal_loop.py` | Human goal + mock-first Oracle; next turn remains Human-gated |
| CENT-durable | Centaur | Durable completed_steps resume | ✅ | `run_meta.py`, `room.py`, `sessions/_regression/durable_completed_steps/` | |
| MD-PROJECT | Prompt | PROJECT.md + per-dir AGENTS hierarchy | ✅ | `session_guidance.py`, `workspace_md.py:resolve_agents_md_for_guidance()`, `repo_tree_context.py` | root flat fallback; plan path → ancestor chain in `session_guidance` |
| MD-PLATFORM | Prompt | PLATFORM.md protocol injection | ✅ | `.agent-lab/PLATFORM.md`, `platform_md.py`, `tests/test_platform_md.py` | inject cap 500 chars |
| LC-clarifier | LazyCodex | session_clarifier Socratic gate | ✅ | `session_clarifier.py`, `room.py`, `tests/test_session_clarifier.py` | `AGENT_LAB_CLARIFIER=1`; discuss + plan mode |
| ML-C-omo | omo | Mission Loop Layer 6 FSM (C안) | ✅ | `mission_loop.py`, `routers/mission_loop.py`, `tests/test_mission_loop.py`, `sessions/_regression/mission_loop_*`, [MISSION-LOOP-C-OMO.md](MISSION-LOOP-C-OMO.md) | Discuss ↔ Execute ↔ Verify; Momus-lite gate; 3 smoke baselines |
| ML-P0 | omo | MISSION_DEFINE / verified_loop bridge | ✅ | `verified_loop.py` hooks in `mission_loop.py`, `test_verified_approve_enables_mission` | |
| ML-P2 | omo | Plan gate Momus-lite | ✅ | `evaluate_plan_gate()`, `run_plan_gate()`, `mcp_warnings` | |
| ML-P3 | omo | Execute queue + autorun dry-run | ✅ | `maybe_advance_mission()`, merge/dry-run hooks, `test_maybe_advance_dry_run_mock` | |
| ML-P4 | omo | Verify → Discuss recovery | ✅ | `run_mission_discuss_recovery()`, repair cap tests | |
| ML-P5 | omo | Wisdom notepad | ✅ | `ensure_mission_notepads()`, `append_wisdom_note()`, `build_mission_wisdom_block` | `.agent-lab/missions/<id>/` |
| ML-TB | PLUGIN | Session MCP allowlist pass-through | ✅ | `session_plugin_runtime.py`, `mcp_spec_export.py`, `tests/test_session_plugin_runtime.py` | Claude overlay + Codex transport |
| ML-TC | UI | Mission Overview + context layers | ✅ | `MissionOverviewSection.tsx`, `context_layers.py`, `repo_tree_context.py` | Work + Inspector |
| ML-TD | UX | Stop / pause / permission | ✅ | `run_control.py`, `pause_mission_loop`, `cursor_agent._wait_cursor_run`, `PluginPanel` cursor hint | `children_terminated` on cancel API |
| ML-P1 | omo | Mission Conductor UI polish | ✅ | `WorkStatusBar`, `WorkPanel`, `MissionOverviewSection`, USER-GUIDE §4.3·§28 | 5-step stepper + paused badge + resume phase highlight |

---

## Partial

_(none — mission UI + per-dir hierarchy closed 2026-06-08)_

---

## Future — fixture / smoke tickets (no code yet)

These are **acceptance criteria only**.

| ID | Item | Design doc |
|----|------|------------|
| _(none — HOOK-COMM core shipped 2026-06-07)_ | | |

_(Dev-tool MD items in §Dev-tool are shipped.)_

---

## Dev-tool & prompt layer (MD-WRITING-PLAN items)

These items affect **Agent Lab development workflow** or **agent prompt quality**, not Room runtime features.  
They are tracked here but do not belong in the runtime feature roadmap.

| ID | Source | Item | Status | Evidence | Notes |
|----|--------|------|--------|----------|-------|
| CC-CLAUDE | Claude Code | `CLAUDE.md` dev guide | ✅ | `CLAUDE.md` | Root dev guide; see MD-WRITING-PLAN |
| CC-hooks | Claude Code | `.claude/settings.json` hooks | ✅ | `.claude/settings.json`, `.claude/hooks/`, `tests/test_claude_hooks.py` | PostEdit ruff/prettier; Stop pytest tail; **not** `room_hooks.py` (runtime server hooks) |
| CC-rules | Claude Code | `.claude/rules/*.md` path rules | ✅ | `.claude/rules/python-backend.md`, `.claude/rules/react-frontend.md`, `tests/test_claude_rules.py` | path-scoped; see MD-WRITING-PLAN §파일2 |
| CC-skills | Claude Code | `.claude/skills/` subagent skills | ✅ | `.claude/skills/*`, `project_memory.py`, `scripts/init_project_memory.py` | smoke-and-score, regression-check, init-project-memory |
| MD-PROJECT | Prompt | PROJECT.md workspace injection | ✅ | `session_guidance.py` | Shipped |
| MD-PLATFORM | Prompt | PLATFORM.md externalization | ✅ | `.agent-lab/PLATFORM.md`, `platform_md.py` | inject via session_guidance |
| MD-P3 | Prompt | AGENTS.md + SHARED_CONTEXT injection | ✅ | `workspace_md.py`, `tests/test_workspace_md.py` | Workspace-root flat `AGENTS.md` + `SHARED_CONTEXT.md` (replaces LazyCodex hierarchical AGENTS) |

---

## Next implementation candidates

| Priority | ID | Suggested next action |
|----------|-----|-----------------------|
| P3 | HOOK-COMM-migrate | `AGENT_LAB_LEGACY_ENDORSE=0` + regression fixtures; live envelope KPI re-baseline |

---

## Related docs

- [Documentation index (README)](README.md)
- [External refs plan (ideas)](EXTERNAL-REFS-PLAN.md)
- [Hook · Communicate reform](HOOK-COMMUNICATE-REFORM.md)
- [Room reinforcement](ROOM-REINFORCEMENT.md)
- [Ops runbook](OPS-RUNBOOK.md)
- [Execute worktree reform](EXECUTE-WORKTREE-REFORM.md)
