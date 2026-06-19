# Planner — Structural Debt: God-Module Decomposition (`plan_execute.py`, `mission_loop.py`)

## Context (evidence-grounded)
- `src/agent_lab/plan_execute.py` = **2,282 lines**, 10 public + ~50 private symbols. Two monster functions: `run_dry_run` (~500 lines), `resolve_execution` (~300 lines).
- `src/agent_lab/mission_loop.py` = **1,895 lines**, 33 public + many private symbols. Clear FSM/notepad clusters.
- **Decomposition convention already exists and is mature**: sibling leaf modules `plan_execute_{git,worktree,snapshot,isolation,merge,paths}.py` (96–312 lines) and `mission_{scheduler,tick,templates,board}.py` (162–460 lines). AGENTS.md documents `plan_execute*.py` as a glob family. The two cores are the **residual, not-yet-decomposed** files.
- Blast radius: 59 files reference these modules, but the dominant pattern is **function-local lazy imports** of *public* entrypoints. Public entrypoints are the externally-imported surface; private `_helpers` are internal.
- Baseline (must be preserved): `ruff check` clean on both files; fast lane ~1101 passing / 0 failing (prior session); `mypy src/agent_lab` lenient baseline (`files = ["src/agent_lab"]`).

## "Production" framing
Value-in-use dogfooding work: smaller modules = lower context-load cost per edit, faster navigation, safer surgical changes. NOT a behavior change. Success = the same system, in smaller files, with the test suite as the unchanged behavioral oracle.

## Principles
1. **Behavior-preserving, move-only.** No logic edits. Each extraction is a pure code move; diffs read as relocation, not rewrite. Test suite is the oracle.
2. **Public API immovable.** Externally-imported entrypoints keep their original import path (`agent_lab.plan_execute.X`, `agent_lab.mission_loop.X`): they stay in the core file, or are re-exported from it. Zero churn at the 59 call sites unless a site is intentionally migrated AND verified.
3. **Extend the existing convention; no parallel patterns.** New modules follow `plan_execute_<concern>.py` / `mission_<concern>.py` naming and leaf-helper shape.
4. **Leaf-only extraction; no new import cycles.** Move clusters that depend downward (helpers), not upward (orchestrators). Cross-references that would cycle stay as function-local imports (repo's dominant convention).
5. **Incremental + independently shippable.** Each phase lands green on its own; never requires both modules done at once.

## Decision Drivers (top 3)
1. **Risk of silent breakage across 59 import sites** (many lazy/local) — must be near-zero. Favors keeping/re-exporting the public surface over hard-moving it.
2. **Match the mature existing convention** — siblings already prove the `*_<concern>.py` leaf pattern; reuse it exactly.
3. **Verifiability of "no behavior change"** — the win is real only if the full fast lane stays green at the same count with move-only diffs.

## Viable Options

### Option A — Façade-preserving leaf extraction *(RECOMMENDED)*
Extract private helper clusters out of each core into new/existing `*_<concern>.py` leaf modules. **Public entrypoints stay in the core file** (thinner orchestration façade). Externally-used *public* helpers that move (e.g. mission notepad/wisdom) are **re-exported** from the core for back-compat. Core imports the extracted helpers.
- Pros: ~zero churn at 59 call sites; lowest risk; matches convention exactly; each extraction independently testable & reversible; lazy-import sites untouched.
- Cons: cores still hold the two giant functions (`run_dry_run`, `resolve_execution`) — they shrink but stay monolithic; a few re-export lines linger; must guard against cycles.

### Option B — Hard move + rewire all call sites
Move helpers AND public entrypoints into new modules; update all 59 import sites (incl. function-local lazy imports) via `lsp rename`/`references`; delete the façade.
- Pros: cleanest final import graph; explicit symbol homes; no lingering re-exports.
- Cons: high churn & review burden; lazy/local imports are grep-fragile and easy to miss; largest blast radius and merge-conflict surface. Disproportionate risk for a debt cleanup.

### Option C — In-place sectioning only
Section headers + split the two giant functions into private helpers in the same files; no new modules.
- Pros: trivial; zero import risk.
- Cons: **does not address the God-module debt** — files stay 2k+ lines. Fails the goal. (Folded into Option A as an optional in-module sub-step.)

**Chosen: Option A.** Lowest risk, convention-matching, incremental; public-API-immovable is directly satisfiable (private helpers carry no external risk; the few externally-used public helpers get re-exports).

## Proposed decomposition map

### Phase 1 — `plan_execute.py` (2,282 -> target <= ~900 in core)
Extract `_`-prefixed internal clusters into leaf modules; verify each helper has no external importer first (`lsp references`):
- `plan_execute_status.py` <- approval/status: `_approve_status`, `_artifact_approve_block_reason`, `_count_existed_files`, `_count_existed_in_paths`, `_split_touched_paths`, `_needs_artifact_review`, `_paths_outside_expected`, `_mark_rejected_tasks`, `_mark_approved_effects`, `_execution_approval_record`, `_append_execution_approval`, `_finalize_auto_merge_meta`, `_pending_execution`, `_update_execution_row`; plus `execution_allows_task_complete` (public — re-export), `PENDING_STATUS`/`_CANCELLABLE_EXECUTION_STATUSES` (move with cluster, re-export `PENDING_STATUS`).
- `plan_execute_verify.py` <- verify/repair: `_execution_verify_action`, `_merged_verify_paths`, `_verify_workspace_root`, `_record_verify_after_merge`, `_repair_prompt`, `_call_repair_agent`, `_append_repair_history`, `_notify_merge_conflict_mission`, `_arm_merge_checkpoint`, `_clear_merge_checkpoint`.
- `plan_execute_prompts.py` <- Cursor prompts: `_inbox_mcp_instructions`, `_cursor_plan_phase_prompt`, `_cursor_implement_phase_prompt`, `_cursor_execute_prompt`, `_extract_draft_summary`, `_call_execute_agent`, `_selected_revision_diff`.
- **Stays in core**: all 10 public entrypoints (`run_dry_run`, `resolve_execution`, `list_plan_actions`, `run_isolation_override`, `revise_pending_execution`, `cancel_open_execution`, `confirm_merge_execution`, `abort_merge_execution`, `reverify_merged_execution`) + glue already delegating to `plan_execute_{git,worktree,merge}.py`.

### Phase 2 — `mission_loop.py` (1,895 -> target <= ~900 in core)
- `mission_notepad.py` <- notepad/wisdom: `mission_notepad_dir`, `mission_notepad_rel`, `ensure_mission_notepads`, `_chat_provenance_ref`, `_plan_provenance_ref`, `_format_provenance`, `_read_notepad_tail`, `list_mission_notepad_summaries`, `_notepad_base_from_run_meta`, `build_mission_wisdom_block`, `append_wisdom_note`, `inject_wisdom_into_prompt` + constants `MISSION_NOTEPAD_FILES`, `_NOTEPAD_HEADERS`, `_NOTEPAD_READ_ORDER`, `MISSION_WISDOM_INJECT_CAP`. **`mission_notepad_dir`, `build_mission_wisdom_block`, `inject_wisdom_into_prompt` are imported externally** (evidence_ledger.py, runtime/context.py) -> re-export from `mission_loop.py` (default; or migrate those ~3 sites via `lsp references`).
- `mission_advance.py` <- phase-advance/verify FSM: `maybe_advance_mission`, `_advance_merge_review`, `_advance_verify_stalled`, `_advance_execute_queue`, `_advance_repair`, `set_execution_phase`, `on_verify_result`, `_on_verify_pass`, `_advance_verify_with_policy`, `_on_verify_fail`, `on_dry_run_complete`, `on_merge_confirm`, `on_merge_abort`, `_find_pending_merge_execution`, `_find_open_execution`. (`maybe_advance_mission`, `mission_autorun_enabled` imported by mission_tick.py -> re-export from core or migrate that one site.)
- **Stays in core**: state/getters, plan gate (`evaluate_plan_gate`, `run_plan_gate`, `after_plan_scribe`, `open_block_reason`), enable/circuit-breaker (`enable_mission_loop`, `trigger_circuit_breaker`, `clear_circuit_breaker`, `is_structural_verify_fail`), pause/resume + payload (`pause_mission_loop`, `resume_mission_loop`, `on_global_run_cancel`, `public_mission_payload`), discuss recovery (`run_mission_discuss_recovery`, `_discuss_recovery_prompt`, `on_structural_execution_failure`).

## Acceptance Criteria (testable)
- AC1: `plan_execute.py` and `mission_loop.py` each <= ~900 lines; new leaf modules each <= ~450 lines.
- AC2: Every externally-imported public symbol still importable from its original path. Probe: `python -c "from agent_lab.plan_execute import run_dry_run, resolve_execution, confirm_merge_execution, abort_merge_execution, list_plan_actions, execution_allows_task_complete, PENDING_STATUS; from agent_lab.mission_loop import get_mission_loop, public_mission_payload, evaluate_plan_gate, after_plan_scribe, enable_mission_loop, maybe_advance_mission, mission_autorun_enabled, on_global_run_cancel, mission_notepad_dir, build_mission_wisdom_block, inject_wisdom_into_prompt"` exits 0.
- AC3: `app.server.main:app` imports cleanly (router wiring intact).
- AC4: `make test-fast` -> same pass count as baseline (~1101), **0 failures** (excluding the 2 known pre-existing integration env failures, not in the fast lane).
- AC5: `ruff check src/agent_lab` clean; `mypy src/agent_lab` no new errors vs baseline.
- AC6: Diffs are move-only — reviewer confirms no logic/constant divergence (each moved constant has exactly one definition home).
- AC7: No new import cycle — import smoke of all touched + new modules succeeds.

## Pre-mortem (3 scenarios — deliberate)
1. **Circular import after extraction.** Moved helper imported at new module top level references something still in core that imports the new module -> ImportError at load. *Mitigation*: extract leaf helpers only (downward deps); keep back-references as function-local imports (repo convention); AC7 import smoke + full fast lane.
2. **Constant/state divergence on a partial move.** A helper reads a module-level constant (`MAX_DIFF_CHARS`, `PENDING_STATUS`, `_CANCELLABLE_EXECUTION_STATUSES`, `MISSION_WISDOM_INJECT_CAP`) left in the core -> duplicated or NameError. *Mitigation*: move each constant with its owning cluster; re-export only where externally referenced; grep every constant before moving; AC6 move-only diff review.
3. **A "private" symbol is actually imported by a test/sibling.** Moving silently breaks collection. *Mitigation*: `lsp references` (catches lazy/local imports) on every symbol before moving; re-export or update the importer; full fast lane as backstop.

## Expanded Test Plan (deliberate)
- **Unit**: existing `tests/test_plan_execute*`, `tests/test_mission_loop*` (+ verify/repair, dry-run, resolve tests) pass unchanged — primary oracle for move-only.
- **Integration**: mission FSM transitions (dry-run->merge->verify->repair), worktree merge (mock), `crash_recovery` reconcile (imports `plan_execute._arm_merge_checkpoint` — verify still reachable wherever it lands; if moved, importer follows or re-export).
- **e2e/smoke**: AC2 import probe, AC3 app-boot import, full `make test-fast`.
- **Observability**: no new logging (move-only). Structural-debt metric = before/after line counts in the final ADR; ruff/mypy delta = 0 new findings.

## Execution sequencing (for handoff, not executed here)
1. Phase 1 = one extraction at a time (status -> verify -> prompts), `make test-fast` green after each.
2. Phase 2 = notepad -> advance, green after each.
3. Each module move is its own commit-sized unit; no constant left without a single home.
4. Stop-the-line on any new ruff/mypy finding or any fast-lane regression.

## Out of scope (explicit)
- mypy coverage of `app/server` (HTTP layer entirely outside `files = ["src/agent_lab"]`) — a separate, larger debt; not in this plan. (Corrects the prior eval's imprecise "remove room.py mypy exclusion" note; room.py is 564 lines, untyped by mypy *scope*, not by an exclusion.)
- Splitting the two giant functions into multiple public functions (signature changes) — behavior-risking; only optional same-file private extraction is in scope.
- Any logic/performance/API change — strictly structural.
