# FINAL PLAN (pending approval) — Structural Debt: God-Module Decomposition

**Run**: `2026-06-17-structural-debt` · **Mode**: deliberate (auto-enabled: destructive git-merge code + public-API-breakage risk) · **Consensus**: Architect CLEAR/APPROVE + Critic APPROVE (pass 2).
**Status**: PENDING APPROVAL — no source mutated, no execution performed. Approve to hand off to ultragoal.

## Objective
Reduce the two residual God modules to navigable, low-context-load sizes by **behavior-preserving extraction**, extending the repo's existing `*_<concern>.py` leaf-module convention. Strictly structural — the test suite is the unchanged behavioral oracle.

## Target evidence
- `plan_execute.py` 2,282 lines (10 public + ~50 private; giants `run_dry_run` ~500, `resolve_execution` ~300).
- `mission_loop.py` 1,895 lines (33 public + many private).
- Existing convention: `plan_execute_{git,worktree,snapshot,isolation,merge,paths}.py`, `mission_{scheduler,tick,templates,board}.py` (96–460 lines). Baseline: ruff clean, fast lane ~1101 pass/0 fail, `mypy src/agent_lab` lenient.

## Decision (ADR)
- **Decision**: Adopt **Option A — façade-preserving leaf extraction**, in three phases: (1) extract `plan_execute.py` private clusters into `plan_execute_{status,verify,prompts}.py`; (2) extract `mission_loop.py` clusters into `mission_{notepad,advance}.py`; (3) decompose the two giant functions into in-module private step-helpers. Public entrypoints stay in the core; the ≤4 enumerated external movers are migrated to new homes via LSP (re-export reserved for large/unenumerable caller sets).
- **Drivers**: (1) near-zero breakage risk across 59 import sites (many lazy/local); (2) reuse the mature existing convention; (3) verifiability of "no behavior change" via an unchanged green fast lane.
- **Alternatives considered**: B — hard move + rewire every site (cleanest end-state but high churn, grep-fragile lazy imports, disproportionate risk); C — in-place sectioning only (zero risk but does not reduce module size — fails the goal). Both rejected; B's honest-import-graph upside is partially captured by migrate-by-default for the countable surface.
- **Why chosen**: A is the lowest-risk path that actually shrinks the modules, matches convention, is incremental/reversible, and — with the revision's migrate-by-default + Phase 3 + proof-bearing constant invariant — also delivers an honest import graph and non-gameable scope.
- **Consequences**: a few back-compat re-export lines may linger (only where caller sets are large); Phase 3 carries the most extract-method risk and is gated last with a coverage pre-check; net result is 5 new leaf modules (~150–450 lines each), two cores reduced to ≤~900 lines, and (if Phase 3 ships) the two giants reduced to orchestration bodies.
- **Follow-ups**: (i) mypy coverage for `app/server` (HTTP layer entirely outside `files=["src/agent_lab"]`) — separate larger debt; (ii) Phase 3 may be deferred and registered as its own run if the user wants Phases 1–2 shipped first.

## Phases & decomposition map

### Phase 1 — `plan_execute.py` -> ≤~900 (module extraction)
- `plan_execute_status.py`: `_approve_status`, `_artifact_approve_block_reason`, `_count_existed_files`, `_count_existed_in_paths`, `_split_touched_paths`, `_needs_artifact_review`, `_paths_outside_expected`, `_mark_rejected_tasks`, `_mark_approved_effects`, `_execution_approval_record`, `_append_execution_approval`, `_finalize_auto_merge_meta`, `_pending_execution`, `_update_execution_row` + `execution_allows_task_complete` (public, re-export) + `PENDING_STATUS`/`_CANCELLABLE_EXECUTION_STATUSES`.
- `plan_execute_verify.py`: `_execution_verify_action`, `_merged_verify_paths`, `_verify_workspace_root`, `_record_verify_after_merge`, `_repair_prompt`, `_call_repair_agent`, `_append_repair_history`, `_notify_merge_conflict_mission`, `_arm_merge_checkpoint`, `_clear_merge_checkpoint`.
- `plan_execute_prompts.py`: `_inbox_mcp_instructions`, `_cursor_plan_phase_prompt`, `_cursor_implement_phase_prompt`, `_cursor_execute_prompt`, `_extract_draft_summary`, `_call_execute_agent`, `_selected_revision_diff`.
- Stays in core: 10 public entrypoints + glue to existing `plan_execute_{git,worktree,merge}.py`.

### Phase 2 — `mission_loop.py` -> ≤~900 (module extraction)
- `mission_notepad.py`: notepad/wisdom cluster + `MISSION_NOTEPAD_FILES`/`_NOTEPAD_HEADERS`/`_NOTEPAD_READ_ORDER`/`MISSION_WISDOM_INJECT_CAP`. Migrate external sites: `evidence_ledger.py` (`mission_notepad_dir`), `runtime/context.py` (`build_mission_wisdom_block`, `inject_wisdom_into_prompt`).
- `mission_advance.py`: phase-advance/verify FSM cluster. Migrate external site: `mission_tick.py` (`maybe_advance_mission`, `mission_autorun_enabled`).
- Stays in core: state/getters, plan gate, enable/circuit-breaker, pause/resume + payload, discuss recovery.

### Phase 3 — giant-function decomposition (highest risk; gated last; deferrable)
- Split `run_dry_run`/`resolve_execution` into named private step-helpers within `plan_execute.py` (NO public-signature change). Public bodies reduce to ordered calls + identical control flow.
- **Gate**: run only after Phases 1–2 green; before extracting, confirm branch coverage (dry-run, resolve, merge-conflict, paths-outside-expected, verify-retry) and add a characterization test where a branch is uncovered; one move-only step-helper at a time.

## Acceptance Criteria
- AC1: each core ≤~900 lines post its extraction phase; each new leaf module ≤~450.
- AC2: import probe (post Phase 1/2) exits 0 — plan_execute publics from original path; mission notepad/advance from new homes (callers migrated).
- AC3: `app.server.main:app` imports cleanly.
- AC4: `make test-fast` = baseline count (~1101), 0 failures (2 known pre-existing integration env failures excluded; not in fast lane).
- AC5: `ruff check src/agent_lab` clean; `mypy src/agent_lab` no new errors.
- AC6 (proof-bearing): one definition home per moved constant — `git grep` invariants in QA artifact.
- AC7: no new import cycle — import smoke of all touched + new modules.
- AC8 (anti-gaming): deliverable states which scope shipped (module extraction P1–2 and/or function decomposition P3); line-count alone ≠ Phase 3.

## Pre-mortem (3) — carried, all mitigated
1. Circular import -> leaf-only + function-local back-refs + AC7/full lane.
2. Constant/state divergence -> move-with-cluster + AC6 grep-proof.
3. "Private" symbol externally imported -> `lsp references` pre-flight + re-export/migrate + full lane.

## Expanded test plan — carried
Unit (existing plan_execute/mission_loop tests), integration (FSM transitions, worktree merge mock, crash_recovery reconcile on `_arm_merge_checkpoint`), e2e/smoke (AC2/AC3 + full `make test-fast`), observability (line-count metric in deliverable; ruff/mypy delta = 0).

## Out of scope
`app/server` mypy coverage; public-API signature changes; any logic/perf change.

## Recommended execution path
**ultragoal** (goal-tracked, verification-gated) — fits the move-only + per-phase green-lane discipline. `team` only if interactive tmux worker parallelization is wanted (not required). Phases are independently shippable: P1 -> P2 -> P3, green fast lane after each; P3 deferrable.
