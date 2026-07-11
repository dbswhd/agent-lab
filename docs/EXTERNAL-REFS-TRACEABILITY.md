# External refs plan — traceability matrix

Maps items in [`EXTERNAL-REFS-PLAN.md`](archive/rfcs/EXTERNAL-REFS-PLAN.md) to **shipped code**, **regression/smoke evidence**, or **future fixture tickets**.
This document is the hub for **plan vs reality**. It does not explain *why* an item was adopted — see PLAN §anchor for that context.

**Status legend:** ✅ shipped · 🔶 partial · ⬜ future · ❌ dropped  
**Related:** [EXTERNAL-REFS-PLAN.md](archive/rfcs/EXTERNAL-REFS-PLAN.md) (why/what) · [MD-WRITING-PLAN.md](MD-WRITING-PLAN.md) (MD authoring guide)
**Dev-tool cross-ref:** `CC-CLAUDE` is tracked in [§Dev-tool](#dev-tool--prompt-layer-md-writing-plan-items) only (not duplicated in the runtime table below).

---

## Shipped (evidence in repo)

| ID | Source | Item | Status | Evidence | Notes |
|----|--------|------|--------|----------|-------|
| L1 | LazyCodex | CLI retry loop | ✅ | `src/agent_lab/cli_retry.py`, `tests/test_cli_retry.py`, R-P0 | Layer 1 |
| L2 | LazyCodex | Consensus loop | ✅ | `src/agent_lab/room_consensus.py`, `room.py` | Layer 2, cap_rounds/calls |
| LC-oracle | LazyCodex | Oracle verified completion (mock-first) | ✅ | `oracle_core.py`, `plan_execute_merge.py:oracle_verify()`, `goal_loop.py`, `tests/test_oracle_core.py`, [LIVE-ORACLE.md](LIVE-ORACLE.md) | Structured VERDICT/EVIDENCE; live via `AGENT_LAB_ORACLE_LIVE=1` |
| LC-L3 | LazyCodex | Execute verify + agent repair loop | ✅ | `verify_after_merge()`, `oracle_verify()`, `src/agent_lab/plan_execute.py`, `/api/sessions/{id}/execute/reverify`, `PlanExecutePanel.tsx`, `sessions/_regression/execute_verify_loop/`, `tests/test_plan_execute_agent_repair.py` | Oracle FAIL opens a fresh Cursor/Codex worktree repair, re-merges, and re-verifies; `MAX_VERIFY_RETRIES=2` |
| PI | Conductor | Git worktree execute + merge | ✅ | `src/agent_lab/plan_execute_*.py`, `sessions/_regression/worktree_*`, `tests/test_plan_execute_worktree.py` | Phase I M0–M4 |
| CON-diff | Conductor | Diff hunk inline revise | ✅ | `PlanExecutePanel.tsx`, `revise_pending_execution()`, `tests/test_plan_execute_revise_api.py` | Human hunk comment → fresh worktree re-diff → re-approve |
| PI-executed | Conductor | Merged diff archive | ✅ | `plan_execute_merge.py:archive_executed_diff()`, `tests/test_executed_archive.py` | `sessions/<id>/executed/{exec_id}.json` |
| PI-ops | Conductor | Live worktree Go/No-Go | ✅ | `docs/LIVE-CURSOR-WORKTREE-DRY-RUN.md`, `scripts/live_cursor_worktree_dry_run.py`, Tier B in `docs/OPS-RUNBOOK.md` | Manual, not CI |
| PI-ops-C | Conductor | Live merge operator | ✅ | `docs/LIVE-MERGE-OPERATOR.md`, `scripts/live_cursor_worktree_merge_run.py`, `make verify-ops-live-merge` | Disposable repo only |
| E-smoke | Room | BLOCK/CHALLENGE governance | ✅ | `sessions/_regression/objection_blocks_execute/`, `envelope_consensus_endorse/`, `scripts/smoke_room.py` | 38 baselines |
| LC-router | LazyCodex | Topic category routing (창발 예산) | ✅ | `topic_router.py`, `tests/test_topic_router.py`, `sessions/_regression/category_escalation_quick_to_deep/` | quick/standard/deep/critical; 충돌 act 자동 에스컬레이션; `AGENT_LAB_TOPIC_ROUTER=0` 롤백. LazyCodex 대비: 라우팅 대상이 워커가 아니라 합의 깊이 — [MISSION-LOOP-C-OMO.md](MISSION-LOOP-C-OMO.md) §4 |
| EM-P1 | Emergence | 창발 KPI 1급 속성화 | ✅ | `emergence_kpis.py`, `tests/test_emergence_kpis.py`, `sessions/_regression/emergence_hybrid_plan/`, `AGENT_LAB_MOCK_ACT_SCRIPT` | hybrid_action_rate · challenge_yield · amend_chain · act 텔레메트리 (score_session 통합) |
| EM-P3 | Emergence | discuss 충돌 상태화 + 품질 게이트 | ✅ | `room_objections.py`, `tests/test_discuss_objections.py`, `sessions/_regression/discuss_challenge_resolved/` | endorse 자동 해소(BLOCK 제외) · 무충돌 deep/critical 강제 反 · `consensus.quality` |
| EM-P4 | Emergence | 재조합 라운드 + anchor 계보 | ✅ | `room_consensus.py`, `tests/test_recombination.py`, `sessions/_regression/recombination_synthesis/` | route.recombination on/auto/off; anchor id/parent_id 체인 + AMEND delta |
| EM-P5 | Emergence | stigmergy 루프 + 창발 벤치 | ✅ | `context_bundle.py` wisdom R1 주입, `[LEARNED:]` 수확, `inbox_mcp_server.py:wisdom_search`, `scripts/emergence_bench.py`, `sessions/_benchmark/topics/emergence-v1.json`, `docs/EMERGENCE-BENCH.md`, `tests/test_stigmergy_loop.py` | `make emergence-bench` (mock, judge=heuristic); live는 `AGENT_LAB_EMERGENCE_BENCH_LIVE=1` CI 금지 |
| F-R3 | Room | Asymmetric `capability_cwd` | ✅ | `sessions/_regression/specialist_asymmetric_cwd/`, `topic_router` topology + `seed_capabilities_for_route`, `scripts/smoke_room.py` | Route-driven producer_reviewer (Settings 분업 UI 퇴출) |
| RO-P1 | Fugu / Harness | Role orchestration (topic_router + role_plan) | ✅ | `role_plan.py`, `topic_router.py`, `room/turn_routing.py`, `sessions/_regression/producer-reviewer-roles/`, `tests/test_role_plan.py`, `tests/test_turn_routing.py` | Composer preset fast/supervisor only; topology data not preset id |
| H-P1 | H4 | score_session CI | ✅ | `scripts/score_session.py`, `tests/test_session_score_ci.py`, `.github/workflows/ci.yml` | |
| H-P2 | Room | Benchmark catalog + delegate replay | ✅ | `sessions/_benchmark/`, `tests/test_benchmark_catalog.py`, `tests/test_room_delegate_replay.py` | Offline R1–R5 catalog; PLAN Phase 3; see [archive/rfcs/ROOM-REINFORCEMENT.md](archive/rfcs/ROOM-REINFORCEMENT.md) |
| H4-weekly | H4 | Weekly KPI + M4 gates | ✅ | `scripts/score_sessions_weekly.py`, `src/agent_lab/session_score_weekly.py` | |
| H4-ops | H4 | Weekly ops artifact | ✅ | `format_weekly_report_markdown`, `make score-weekly`, `sessions/_reports/` | gitignored artifacts |
| H4-ops-live | H4 | Last live check in weekly | ✅ | `discover_live_ops_reports`, `tests/test_weekly_live_ops_summary.py` | Tier B/C JSON scan |
| ops-P0 | Platform | FastAPI lifespan | ✅ | `app/server/main.py` lifespan | |
| ops-P2 | Platform | Router split | ✅ | `app/server/routers/*`, `app/server/main.py` | |
| ops-verify | Platform | Manual ops routine | ✅ | `make verify-ops`, `tests/test_verify_ops_makefile.py`, `docs/OPS-RUNBOOK.md` | Tier A |
| ops-flags | Platform | AGENT_LAB_* flag discoverability | ✅ | `runtime_flags.py`, `GET /api/health/flags`, `scripts/list_flags.py`, `make list-flags`, `tests/test_health_flags_api.py` | 79 registry entries; path values masked |
| N9-verify | Platform | External verify API service | ✅ | `app/server/routers/evidence_api.py`, `app/server/verify_audit.py`, `docs/VERIFY-API.md`, `scripts/n9_verify_consumer.py`, `tests/test_n9_verify_api.py`, `sessions/_examples/n9-gjc-handoff.json` | `POST /v1/verify` audit headers; GJC handoff consumer |
| R-P0 | Room | Partial turn | ✅ | `src/agent_lab/room.py`, `docs/STABILITY.md` | |
| R-P1 | Room | F2 artifact-only R2 | ✅ | `sessions/_regression/specialist_r2_artifact_only/`, `context_bundle.py` | |
| HOOK-COMM | Hook · Communicate reform | ✅ | `reply_policy.py`, `room/hooks.py`, `gate_snapshot.py`, `communicate_kpis.py`, `sessions/_regression/envelope_consensus_endorse/`, `make verify-hooks`, USER-GUIDE §9.8 | `LEGACY_ENDORSE` default **off** (2026-06-08) — [HOOK-COMMUNICATE-REFORM.md](./HOOK-COMMUNICATE-REFORM.md) |
| CMD-RDP | Fable fusion | Room worker dispatch protocol | ✅ | `room_dispatch.py`, `room_dispatch_intents.py`, `docs/ROOM-DISPATCH-PROTOCOL.md`, `tests/test_room_dispatch.py` | `DELEGATE` + `DISPATCH parallel:`; ledger `dispatch_ledger[]`; ≠ `runtime.dispatch()` |
| CMD-hooks | Fable fusion | Dispatch hook lifecycle | ✅ | `room/hooks.py` (`pre_dispatch`, `post_dispatch`), `.agent-lab/hooks.example.toml` | Turn-boundary hooks; per-agent sandwich unchanged |
| CMD-fanout | Fable fusion | Parallel scoped worker fan-out | ✅ | `room_dispatch.py`, `AGENT_LAB_DISPATCH_MAX_FANOUT`, `sessions/_regression/dispatch_parallel_explore/` | Cap independent of LC-router (EM-P2) |
| UX-P2 | Room | Objection resolve UX | ✅ | `PlanExecutePanel.tsx`, `RoomTaskBar.tsx` | |
| Bridge | Room | Cursor bridge degraded | ✅ | `sessions/_regression/bridge_degraded_health/`, H-P3 tests | |
| CENT-env | Centaur | Subprocess env allowlist | ✅ | `src/agent_lab/subprocess_env.py`, `claude_cli.py`, `codex_cli.py`, `cursor_bridge.py`, `tests/test_subprocess_env.py` | [PLAN §3.2](archive/rfcs/EXTERNAL-REFS-PLAN.md#32-subprocess-credential-분리) |
| LC-L4 | LazyCodex | Adversarial gate (mock + UI) | ✅ | `adversarial_gate.py`, `PlanExecutePanel.tsx`, `docs/LC-L4-ADVERSARIAL-LIVE.md`, `sessions/_regression/adversarial_gate_lgtm/` | Mock default; live opt-in in LC-L4 doc |
| LC-L5 | LazyCodex | Goal-driven session loop | ✅ | `goal_loop.py`, `RoomChat.tsx`, `docs/GOAL-LOOP.md`, `sessions/_regression/goal_loop_achieved/`, `tests/test_goal_loop.py` | Human goal + mock-first Oracle; legacy when plan workflow ON — [archive/rfcs/PLAN-WORKFLOW.md](archive/rfcs/PLAN-WORKFLOW.md) |
| PW-1 | 4C / Merge Verified | Plan-First workflow FSM | ✅ | `plan_workflow.py`, `app/server/routers/plan_workflow.py`, `PlanApprovalPanel.tsx`, `docs/archive/rfcs/PLAN-WORKFLOW.md`, `sessions/_regression/plan_workflow_approved/`, `tests/test_plan_workflow.py` | Clarify inbox → scribe → peer review → Human plan approve → mission/execute |
| CENT-durable | Centaur | Durable completed_steps resume | ✅ | `run_meta.py`, `room.py`, `sessions/_regression/durable_completed_steps/` | |
| MD-PROJECT | Prompt | PROJECT.md + per-dir AGENTS hierarchy | ✅ | `session_guidance.py`, `workspace_md.py:resolve_agents_md_for_guidance()`, `repo_tree_context.py` | root flat fallback; plan path → ancestor chain in `session_guidance` |
| MD-PLATFORM | Prompt | PLATFORM.md protocol injection | ✅ | `.agent-lab/PLATFORM.md`, `platform_md.py`, `tests/test_platform_md.py` | inject cap 500 chars |
| LC-clarifier | LazyCodex | session_clarifier Socratic gate | ✅ | `session_clarifier.py`, `room.py`, `tests/test_session_clarifier.py` | `AGENT_LAB_CLARIFIER=1`; discuss + plan mode |
| ML-C-omo | omo | Mission Loop Layer 6 FSM (C안) | ✅ | `mission_loop.py`, `routers/mission_loop.py`, `tests/test_mission_loop.py`, `tests/test_mission_loop_e2e.py`, `sessions/_regression/mission_loop_*`, [MISSION-LOOP-C-OMO.md](MISSION-LOOP-C-OMO.md) | Discuss ↔ Execute ↔ Verify; Momus-lite gate; 7 smoke baselines (plan_reject · verify_repair · discuss_recovery 추가) |
| ML-P0 | omo | MISSION_DEFINE / verified_loop bridge | ✅ | `verified_loop.py` hooks in `mission_loop.py`, `test_verified_approve_enables_mission` | |
| ML-P2 | omo | Plan gate Momus-lite | ✅ | `evaluate_plan_gate()`, `run_plan_gate()`, `mcp_warnings` | |
| ML-P3 | omo | Execute queue + autorun dry-run | ✅ | `maybe_advance_mission()`, merge/dry-run hooks, `test_maybe_advance_dry_run_mock` | |
| ML-P4 | omo | Verify → Discuss recovery | ✅ | `run_mission_discuss_recovery()`, repair cap tests | |
| ML-P5 | omo | Wisdom notepad | ✅ | `ensure_mission_notepads()`, `append_wisdom_note()`, `build_mission_wisdom_block` | `.agent-lab/missions/<id>/` |
| ML-TB | PLUGIN | Session MCP allowlist pass-through | ✅ | `session_plugin_runtime.py`, `mcp_spec_export.py`, `tests/test_session_plugin_runtime.py` | Claude overlay + Codex transport |
| ML-TC | UI | Mission Overview + context layers | ✅ | `MissionOverviewSection.tsx`, `context_layers.py`, `repo_tree_context.py` | Work + Inspector |
| ML-TD | UX | Stop / pause / permission | ✅ | `run_control.py`, `pause_mission_loop`, `cursor_agent._wait_cursor_run`, `PluginPanel` cursor hint | `children_terminated` on cancel API |
| ML-P1 | omo | Mission Conductor UI polish | ✅ | `WorkStatusBar`, `WorkPanel`, `MissionOverviewSection`, USER-GUIDE §4.3·§28 | 5-step stepper + paused badge + resume phase highlight |
| MB-9 | OpenHarness | Readiness API + composer hint | ✅ | `readiness.py`, `GET /api/health/readiness`, `ReadinessComposerBar.tsx`, `tests/test_readiness_api.py` | No model calls |
| MB-1 | Paperclip | Mission board schema + Work UI | ✅ | `mission_board.py`, `MissionBoardStrip.tsx`, runtime snapshot | goal_chain + checkout |
| MB-2 | Paperclip | Turn budget meter | ✅ | `mission_board.py`, `TurnBudgetSection.tsx`, Work status bar | `turn_budget` in run.json |
| MB-4 | GJC/OmO | Evidence ledger stream | ✅ | `evidence_ledger.py`, `EvidenceTimeline.tsx`, `GET …/evidence`, `sessions/_regression/evidence_ledger_stream/` | `.agent-lab/missions/<id>/evidence.jsonl` |
| MB-5 | Conductor | Merge Checks SSOT | ✅ | `merge_checks.py`, `MergeChecksPanel.tsx` | merge CTA gate |
| MB-3 | OmO | Five evidence gates | ✅ | `evidence_gates.py`, `EvidenceGatesPanel.tsx`, `sessions/_regression/evidence_gates_merged_ok/` | executions[].evidence_gates |
| MB-7 | GJC | Clarifier interview v2 | ✅ | `session_clarifier.py`, `GET/POST …/clarifier-interview*`, `RoomChat.tsx` | inbox harvest + answers API |
| MB-6 | Conductor | Worktree setup/verify hooks | ✅ | `worktree_hooks.py`, `plan_execute.py`, `tests/test_plan_execute_worktree.py` | `.agent-lab/worktree.yaml` |
| ABSORB-W1 | CC/Codex/Conductor | Workspace card + plan contract (TL;DR/Must-NOT/waves/evidence) | ✅ | `WorkspaceCard.tsx`, `PlanExecutePanel.tsx`, `ROOM_SCRIBE`, `validate_plan_actions_format` soft_issues, [ABSORB-CC-CODEX-2026-07.md](ABSORB-CC-CODEX-2026-07.md), `tests/test_plan_actions_validation.py` | 5모트 유지 |
| ABSORB-P1 | CC/Codex | Needs input badge + mid-run steer | ✅ | `NeedsInputBadge.tsx`, `needsInputStatus.ts`, `steer.py`, `POST /api/sessions/{id}/steer`, `tests/test_steer.py`, `tests/test_absorb_p1_needs_input_steer.py` | Informational steer only — no Inbox/execute gate bypass |
| ABSORB-P1b | CC/Codex | Statusline · notify · monitor · fork | ✅ | `SessionStatusLine.tsx`, `notifyNeedsInput.ts`, `evidence_monitor.py`, `session/fork.py`, `POST …/evidence/monitor`, `POST …/fork`, `tests/test_absorb_wave2_remaining.py`, [ABSORB-CC-CODEX-2026-07.md](ABSORB-CC-CODEX-2026-07.md) | Monitor/fork are read-only / re-approve; no autofix |
| ABSORB-P2-WT | CC/Codex | worktree.yaml baseRef · include · create/remove (**ABS-P2-worktree-yaml**) | ✅ | `worktree_hooks.py`, `execute_isolation.py`, `execute_shared.py`, `execute_worktree.py`, `WorkspaceCard.tsx`, `tests/test_worktree_hooks.py`, [MISSION-BOARD-ADOPTION.md](MISSION-BOARD-ADOPTION.md) §7.3, [ABSORB-CC-CODEX-2026-07.md](ABSORB-CC-CODEX-2026-07.md) | Fail-closed create/setup; remove best-effort; no gate bypass. Remaining ABS-P2 = docs-only / N7 frozen |
| MB-8 | GJC/H7 | External handoff JSON | ✅ | `external_handoff.py`, `runtime/external_runner.py`, `POST …/external-handoff`, `sessions/_regression/external_handoff_attached/` | auto-attach from runner stdout/file |
| MB-10 | Hermes | Wisdom / evidence index | ✅ | `wisdom_index.py`, `WisdomSearchPanel.tsx`, `GET …/wisdom-search`, `sessions/_regression/wisdom_index_built/` | mission-auto; optional cross-session |
| MB-11 | openai-oauth | Codex proxy adapter (dev) | ✅ | `runtime/adapters/codex.py`, `CodexProxyPanel.tsx`, `GET /api/health/codex-proxy` | `AGENT_LAB_CODEX_PROXY=1` |
| RT-H0 | Runtime | Unified harness contract (phases, events, transitions, import audit) | ✅ | `runtime/events.py`, `runtime/transitions.py`, `runtime/import_graph.py`, `runtime/mission_lane.py`, `tests/test_runtime_transition_table.py`, `tests/test_runtime_mission_dispatch.py`, `tests/test_mission_loop_e2e.py`, [RUNTIME-HARNESS-PLAN.md](RUNTIME-HARNESS-PLAN.md) | H0 contract + mission lane (P6, 2026-06-10) |
| RT-H1 | Runtime | Snapshot read path + `GET /runtime` + Work stepper SSOT | ✅ | `runtime/snapshot.py`, `app/server/routers/runtime.py`, `tests/test_runtime_snapshot.py` | H1 read-path |
| RT-H2 | Runtime | Execute lane `dispatch` + `invoke_execute` bridge | ✅ | `runtime/runtime.py`, `runtime/execute_lane.py`, `runtime/invoke_execute.py`, `tests/test_runtime_dispatch.py` | H2 execute lane |
| RT-H3 | Runtime | Discuss lane `discuss_lane` + `invoke_discuss` bridge | ✅ | `runtime/discuss_lane.py`, `runtime/invoke_discuss.py`, `tests/test_runtime_discuss_dispatch.py` | H3 discuss lane |
| RT-H4 | Runtime | PolicyEngine — gate snapshot + hook checks | ✅ | `runtime/policy.py`, `tests/test_runtime_policy.py`, `tests/test_pre_execute_hooks.py` | H4 policy |
| RT-H5 | Runtime | Engine adapters — execute + discuss transport | ✅ | `runtime/adapters/`, `tests/test_runtime_adapters.py` | H5 adapters |
| RT-H6 | Runtime | Boulder/resume — `last_failure` + checkpoint snapshot | ✅ | `runtime/boulder.py`, `tests/test_runtime_boulder.py` | H6 boulder |
| RT-H7 | Runtime | External runner — `tools.yaml` opt-in + allowlist | ✅ | `runtime/external_runner.py`, `tests/test_external_runner.py` | H7 external runner |
| GJC-MAP | GJC | Workflow pipeline ↔ agent-lab integration map | ✅ | [archive/rfcs/GJC-WORKFLOW-PIPELINE.md](archive/rfcs/GJC-WORKFLOW-PIPELINE.md), Learn AI `notes/05-agent-lab/gajae-code-workflow-pipeline.md` | Doc only; adoption backlog AL-009…011 |
| GJC-AUTH | Gajae-code v0.5.4 | Provider picker 기반 CLI 로그인 UX | ✅ | `provider_registry.py`, `auth_runs.py`, `routers/auth.py`, `AuthFlowPanel.tsx`, `ProviderStatusPanel.tsx`, `tests/test_auth_runs.py` | 공식 Codex·Claude·Cursor CLI credential을 source of truth로 사용 |
| PLAN-UX | Gajae Code · Cursor · Claude Code · Codex | 단일 Plan 검토·승인 surface | ✅ | `PlanApprovalPanel.tsx`, `WorkToolPanel.tsx`, `plan_pending.py`, `web/e2e/plan-approval.spec.ts` | HUMAN_PENDING에서 primary CTA 하나; whole-plan hash로 action snapshot 중복 승인 제거; execute·merge·Oracle gate 유지 |
| MCP-INBOX | Human Inbox MCP-first (harvest off, lead/single-flight, source badge) | ✅ | [MCP-FIRST-INBOX.md](MCP-FIRST-INBOX.md), `inbox_mcp_policy.py`, `HumanInboxPanel.tsx`, `tests/test_mcp_first_inbox.py` | Phase A–E; legacy `AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST=1` |

**Planning canonical:** [MISSION-BOARD-ADOPTION.md](MISSION-BOARD-ADOPTION.md) (P1–P4 shipped).

---

## Partial

_(none — MCP-INBOX Phase A–E shipped; see §Shipped.)_

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
| CC-hooks | Claude Code | `.claude/settings.json` hooks | ✅ | `.claude/settings.json`, `.claude/hooks/`, `tests/test_claude_hooks.py` | PostEdit ruff/prettier; Stop pytest tail; **not** `room/hooks.py` (runtime server hooks) |
| CC-rules | Claude Code | `.claude/rules/*.md` path rules | ✅ | `.claude/rules/python-backend.md`, `.claude/rules/react-frontend.md`, `tests/test_claude_rules.py` | path-scoped; see MD-WRITING-PLAN §파일2 |
| CC-skills | Claude Code | `.claude/skills/` subagent skills | ✅ | `.claude/skills/*`, `project_memory.py`, `scripts/init_project_memory.py` | smoke-and-score, regression-check, init-project-memory |
| MD-PROJECT | Prompt | PROJECT.md workspace injection | ✅ | `session_guidance.py` | Shipped |
| MD-PLATFORM | Prompt | PLATFORM.md externalization | ✅ | `.agent-lab/PLATFORM.md`, `platform_md.py` | inject via session_guidance |
| MD-P3 | Prompt | AGENTS.md + SHARED_CONTEXT injection | ✅ | `workspace_md.py`, `tests/test_workspace_md.py` | Workspace-root flat `AGENTS.md` + `SHARED_CONTEXT.md` (replaces LazyCodex hierarchical AGENTS) |

---

## Next implementation candidates

Mission Board backlog (MB-9…MB-11) is **shipped** — see [MISSION-BOARD-ADOPTION.md](MISSION-BOARD-ADOPTION.md) §9.

| Priority | ID | Suggested next action |
|----------|-----|-----------------------|
| — | — | _(MB queue complete; pick from HOOK-COMM / UI Tier 3 or new product work)_ |

---

## Related docs

- [Documentation index (README)](README.md)
- [External refs plan (ideas)](archive/rfcs/EXTERNAL-REFS-PLAN.md)
- [Hook · Communicate reform](HOOK-COMMUNICATE-REFORM.md)
- [Room reinforcement](archive/rfcs/ROOM-REINFORCEMENT.md)
- [Ops runbook](OPS-RUNBOOK.md)
- [Execute worktree reform](archive/rfcs/EXECUTE-WORKTREE-REFORM.md)
