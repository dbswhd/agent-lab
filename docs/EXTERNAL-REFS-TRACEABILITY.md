# External refs plan — traceability matrix

Maps items in [`EXTERNAL-REFS-PLAN.md`](EXTERNAL-REFS-PLAN.md) to **shipped code**, **regression/smoke evidence**, or **future fixture tickets**.  
This document is the hub for **plan vs reality**. It does not explain *why* an item was adopted — see PLAN §anchor for that context.

**Status legend:** ✅ shipped · 🔶 partial · ⬜ future · ❌ dropped  
**Related:** [EXTERNAL-REFS-PLAN.md](EXTERNAL-REFS-PLAN.md) (why/what) · [MD-WRITING-PLAN.md](MD-WRITING-PLAN.md) (MD authoring guide)

---

## Shipped (evidence in repo)

| ID | Source | Item | Status | Evidence | Notes |
|----|--------|------|--------|----------|-------|
| L1 | LazyCodex | CLI retry loop | ✅ | `src/agent_lab/cli_retry.py`, `tests/test_cli_retry.py`, R-P0 | Layer 1 |
| L2 | LazyCodex | Consensus loop | ✅ | `src/agent_lab/room_consensus.py`, `room.py` | Layer 2, cap_rounds/calls |
| PI | Conductor | Git worktree execute + merge | ✅ | `src/agent_lab/plan_execute_*.py`, `sessions/_regression/worktree_*`, `tests/test_plan_execute_worktree.py` | Phase I M0–M4 |
| PI-ops | Conductor | Live worktree Go/No-Go | ✅ | `docs/LIVE-CURSOR-WORKTREE-DRY-RUN.md`, `scripts/live_cursor_worktree_dry_run.py`, Tier B in `docs/OPS-RUNBOOK.md` | Manual, not CI |
| PI-ops-C | Conductor | Live merge operator | ✅ | `docs/LIVE-MERGE-OPERATOR.md`, `scripts/live_cursor_worktree_merge_run.py`, `make verify-ops-live-merge` | Disposable repo only |
| E-smoke | Room | BLOCK/CHALLENGE governance | ✅ | `sessions/_regression/objection_blocks_execute/`, `challenge_revises_metric/`, `scripts/smoke_room.py` | 17 baselines |
| F-R3 | Room | Asymmetric `capability_cwd` | ✅ | `sessions/_benchmark/specialist_asymmetric_cwd/`, `tests/test_benchmark_catalog.py` | Payload meta |
| H-P1 | H4 | score_session CI | ✅ | `scripts/score_session.py`, `tests/test_session_score_ci.py`, `.github/workflows/ci.yml` | |
| H4-weekly | H4 | Weekly KPI + M4 gates | ✅ | `scripts/score_sessions_weekly.py`, `src/agent_lab/session_score_weekly.py` | |
| H4-ops | H4 | Weekly ops artifact | ✅ | `format_weekly_report_markdown`, `make score-weekly`, `sessions/_reports/` | gitignored artifacts |
| H4-ops-live | H4 | Last live check in weekly | ✅ | `discover_live_ops_reports`, `tests/test_weekly_live_ops_summary.py` | Tier B/C JSON scan |
| ops-P0 | Platform | FastAPI lifespan | ✅ | `app/server/main.py` lifespan | |
| ops-P2 | Platform | Router split | ✅ | `app/server/routers/*`, `app/server/main.py` | |
| ops-verify | Platform | Manual ops routine | ✅ | `make verify-ops`, `tests/test_verify_ops_makefile.py`, `docs/OPS-RUNBOOK.md` | Tier A |
| R-P0 | Room | Partial turn | ✅ | `src/agent_lab/room.py`, `docs/STABILITY.md` | |
| R-P1 | Room | F2 artifact-only R2 | ✅ | `sessions/_regression/specialist_r2_artifact_only/`, `context_bundle.py` | |
| UX-P2 | Room | Objection resolve UX | ✅ | `PlanExecutePanel.tsx`, `RoomTaskBar.tsx` | |
| Bridge | Room | Cursor bridge degraded | ✅ | `sessions/_regression/bridge_degraded_health/`, H-P3 tests | |
| CENT-env | Centaur | Subprocess env allowlist | ✅ | `src/agent_lab/subprocess_env.py`, `claude_cli.py`, `codex_cli.py`, `cursor_bridge.py`, `tests/test_subprocess_env.py` | [PLAN §3.2](EXTERNAL-REFS-PLAN.md#32-subprocess-credential-분리) |

---

## Partial

| ID | Source | Item | Status | Evidence | Gap | PLAN ref |
|----|--------|------|--------|----------|-----|----------|
| LC-L4 | LazyCodex | Adversarial gate (mock fixture) | 🔶 | `src/agent_lab/adversarial_gate.py`, `sessions/_regression/adversarial_gate_lgtm/`, `tests/test_adversarial_gate_fixture.py` | Mock-only skeleton; no live Claude, no UI wiring | [§1.5](EXTERNAL-REFS-PLAN.md#15-adversarial-gate-설계-layer-4-상세) |
| LC-clarifier | LazyCodex | session_clarifier Socratic gate | 🔶 | `src/agent_lab/session_clarifier.py` | Feature-flag off (`AGENT_LAB_CLARIFIER`); plan mode not wired | [Part 5 Phase 2](EXTERNAL-REFS-PLAN.md#part-5--통합-우선순위-및-구현-계획) · [§1.3](EXTERNAL-REFS-PLAN.md#13-agent-lab에-도입할-loop-계층) |

---

## Future — fixture / smoke tickets (no code yet)

These are **acceptance criteria only**. Do not add live LLM fixtures until Layer 3/4 design is ticketed.

### Ticket: `execute_verify_loop` (LC-L3)

- **Depends on:** LC-oracle mock `oracle_verify()` (function PR first, or same PR)
- **Folder (future):** `sessions/_regression/execute_verify_loop/`
- **Spec:** After worktree merge, `oracle_verify()` checks `action.verify` field against merged files. FAIL → Human “reverify” button → second worktree dry-run (max 2 retries per [PLAN §1.4](EXTERNAL-REFS-PLAN.md#14-execute-verify-loop-설계-layer-3-상세)).
- **Evidence keys:** `execution.verify_after_merge.status`, `execution.verify_retries`, `oracle.verdict`
- **Tests (future):** mock `verify_after_merge`, mock `oracle_verify`, pytest only
- **UI (future):** `PlanExecutePanel.tsx` — Oracle badge + “에이전트에게 수정 요청” button

### Ticket: `oracle_verified_completion` (LC-oracle)

- **Blocks:** LC-L3 regression fixture (`execute_verify_loop` needs mock `oracle_verify()`)
- **Spec:** Standalone `oracle_verify(action, merged_paths)` in `plan_execute_merge.py`; Claude subprocess (scribe=True) checks `action.verify` against real files. Returns `{verdict, detail, checked_paths}`. Per [PLAN §1.6](EXTERNAL-REFS-PLAN.md#16-oracle-verified-completion-layer-3-심화).
- **Tests (future):** mock oracle call, verify PASS/FAIL routing

### Ticket: `durable_completed_steps` (CENT-durable)

- **Spec:** `run.json` `completed_steps[]` written by `_call_one_agent()` via `patch_run_meta()`. On restart, completed agents skipped. Per [PLAN §3.3](EXTERNAL-REFS-PLAN.md#33-durable-step-centaur-경량판).

### Ticket: `project_md_injection` (MD-PROJECT)

- **Spec:** `session_guidance.py:build_session_guidance_block()` reads `{workspace_root}/.agent-lab/PROJECT.md` (cap 1500 chars) and injects into agent payload. Per [PLAN §1.7](EXTERNAL-REFS-PLAN.md#17-agentsmd-계층--프로젝트-영속-메모리).

### Ticket: `platform_md_externalization` (MD-PLATFORM)

- **Spec:** `src/agent_lab/agents/prompts.py` protocol constants externalized to `.agent-lab/PLATFORM.md` (500 char cap). Per [MD-WRITING-PLAN §파일4](MD-WRITING-PLAN.md).

---

## Dev-tool & prompt layer (MD-WRITING-PLAN items)

These items affect **Agent Lab development workflow** or **agent prompt quality**, not Room runtime features.  
They are tracked here but do not belong in the runtime feature roadmap.

| ID | Source | Item | Status | Evidence | Notes |
|----|--------|------|--------|----------|-------|
| CC-CLAUDE | Claude Code | `CLAUDE.md` dev guide | ⬜ | — | File not in repo yet; see [MD-WRITING-PLAN §파일1](MD-WRITING-PLAN.md) |
| CC-hooks | Claude Code | `.claude/settings.json` hooks | ⬜ | — | Dev-tool only; PostEdit ruff + Stop pytest |
| CC-rules | Claude Code | `.claude/rules/*.md` path rules | ⬜ | — | python-backend, react-frontend; see [MD-WRITING-PLAN §파일2](MD-WRITING-PLAN.md) |
| CC-skills | Claude Code | `.claude/skills/` subagent skills | ⬜ | — | smoke-and-score, regression-check, init-project-memory |
| CON-diff | Conductor | Diff inline revise UI | ⬜ | `PlanExecutePanel.tsx` (approve/reject only) | UI-only; no `sessions/_regression/` fixture |
| MD-PLATFORM | Prompt | PLATFORM.md externalization | ⬜ | — | Replaces hardcoded `prompts.py` constants |
| MD-PROJECT | Prompt | PROJECT.md workspace injection | ⬜ | — | `session_guidance.py` hook needed |

---

## Next implementation candidates

| Priority | ID | Suggested next action |
|----------|-----|-----------------------|
| P1 | LC-oracle | `oracle_verify()` in `plan_execute_merge.py` (mock mode first) |
| P1 | LC-L3 | `execute_verify_loop` fixture skeleton + mock `verify_after_merge` (after LC-oracle) |
| P1 | CENT-durable | `completed_steps[]` in `run_meta.py` + `room.py` |
| P2 | MD-PROJECT | `_read_project_md()` in `session_guidance.py` |
| P2 | CC-CLAUDE | `CLAUDE.md` in repo root (30 min, high dev-velocity impact) |

---

## Related docs

- [External refs plan (ideas)](EXTERNAL-REFS-PLAN.md)
- [Room reinforcement](ROOM-REINFORCEMENT.md)
- [Ops runbook](OPS-RUNBOOK.md)
- [Execute worktree reform](EXECUTE-WORKTREE-REFORM.md)
