# External refs plan — traceability matrix

Maps items in [`EXTERNAL-REFS-PLAN.md`](EXTERNAL-REFS-PLAN.md) to **shipped code**, **regression/smoke evidence**, or **future fixture tickets**.  
This document is the hub for “plan vs reality”; it does not authorize new feature work by itself.

**Status legend:** ✅ shipped · 🔶 partial · ⬜ future · ❌ dropped

---

## Shipped (evidence in repo)

| ID | Source | Item | Status | Evidence | Notes |
|----|--------|------|--------|----------|-------|
| L1 | LazyCodex | CLI retry loop | ✅ | `src/agent_lab/cli_retry.py`, `tests/test_cli_retry.py`, R-P0 | Layer 1 |
| L2 | LazyCodex | Consensus loop | ✅ | `src/agent_lab/room_consensus.py`, `room.py` | Layer 2, cap_rounds/calls |
| PI | Conductor | Git worktree execute + merge | ✅ | `src/agent_lab/plan_execute_*.py`, `sessions/_regression/worktree_*`, `tests/test_plan_execute_worktree.py` | Phase I M0–M4 |
| PI-ops | Conductor | Live worktree Go/No-Go | ✅ | `docs/LIVE-CURSOR-WORKTREE-DRY-RUN.md`, `scripts/live_cursor_worktree_dry_run.py`, Tier B in `docs/OPS-RUNBOOK.md` | Manual, not CI |
| PI-ops-C | Conductor | Live merge operator | ✅ | `docs/LIVE-MERGE-OPERATOR.md`, `scripts/live_cursor_worktree_merge_run.py`, `make verify-ops-live-merge` | Disposable repo only |
| E-smoke | Room | BLOCK/CHALLENGE governance | ✅ | `sessions/_regression/objection_blocks_execute/`, `challenge_revises_metric/`, `scripts/smoke_room.py` | 16 baselines |
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

---

## Partial

| ID | Source | Item | Status | Evidence | Gap |
|----|--------|------|--------|----------|-----|
| CC-CLAUDE | Claude Code | CLAUDE.md dev guide | ⬜ | — | Not in repo; see PLAN Part 4.1 |
| CC-hooks | Claude Code | `.claude/settings.json` hooks | ⬜ | — | Dev-tool layer; not Agent Lab runtime |
| CENT-env | Centaur | Subprocess env allowlist | ⬜ | `claude_cli.py`, `codex_cli.py`, `cursor_bridge.py` | Full parent env still inherited |
| CON-diff | Conductor | Diff inline revise | ⬜ | `PlanExecutePanel.tsx` | Approve/reject only |
| LC-PROJECT | LazyCodex | PROJECT.md memory | ⬜ | — | Not injected in `context_bundle` |

---

## Future — fixture / smoke tickets (no code yet)

These are **acceptance criteria only**. Do not add live LLM fixtures until Layer 3/4 design is ticketed.

### Ticket: `execute_verify_loop`

- **Folder (future):** `sessions/_regression/execute_verify_loop/`
- **Spec:** After worktree merge, post-merge verify FAIL → Human “reverify” → second worktree dry-run (max 2 retries per PLAN Layer 3).
- **Evidence keys:** `execution.verify_after_merge.status`, `execution.verify_retries`
- **Tests (future):** mock `verify_after_merge`, pytest only

### Ticket: `adversarial_gate_lgtm`

- **Folder (future):** `sessions/_regression/adversarial_gate_lgtm/`
- **Spec:** dry-run execution record includes `adversarial_note` (string); UI shows non-blocking badge; `"LGTM"` vs warning text.
- **Tests (future):** mock Claude adversarial call, no live LLM

### Ticket: `durable_completed_steps`

- **Folder (future):** `sessions/_regression/durable_completed_steps/`
- **Spec:** `run.json` `completed_steps[]` survives round boundary; restart resume skips completed agents (Centaur P1).

---

## Next implementation candidates (from PLAN priority matrix)

| Priority | ID | Suggested next PR |
|----------|-----|-------------------|
| P0 | CENT-env | Subprocess env allowlist (XS, 3 files) |
| P1 | LC-L4 | Adversarial gate fixture skeleton + mock |
| P1 | LC-L3 | Execute verify loop fixture skeleton + mock |
| P1 | CENT-durable | `completed_steps` in run_meta |

---

## Related docs

- [External refs plan (ideas)](EXTERNAL-REFS-PLAN.md)
- [Room reinforcement](ROOM-REINFORCEMENT.md)
- [Ops runbook](OPS-RUNBOOK.md)
- [Execute worktree reform](EXECUTE-WORKTREE-REFORM.md)
