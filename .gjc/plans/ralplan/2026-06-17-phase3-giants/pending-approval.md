# FINAL PLAN (pending approval) — Phase 3: Giant-Function Decomposition

**Run** `2026-06-17-phase3-giants` · **Consensus**: Architect CLEAR/APPROVE + Critic APPROVE (1 pass). **Status**: PENDING APPROVAL — no source mutated. Approve to hand off to ultragoal.

## Objective
Convert the two unreadable functions in `plan_execute.py` into short orchestration bodies + named private step-helpers, **behavior-preserving, public signatures unchanged**. This fixes the function-level "God" debt that Phases 1/2 (module extraction) intentionally left.

## ADR
- **Decision**: **Option A — conservative in-module pure-seam extract-method.** Extract only well-bounded blocks (single output, no early-return-to-outer, no broken closure capture) into `_`-prefixed helpers placed adjacent to their caller. Leave high-coupling blocks (validation early-returns, isolation/worktree `_record_blocked`, agent-invocation `_on_activity`) inline.
- **Drivers**: (1) extract-method risk on irreversible git/merge code; (2) branch coverage is the only behavioral oracle; (3) the win is readable, named step-helpers — not a file-size number.
- **Alternatives**: B — move giants' logic to new modules for <=900 *file* size: rejected (threads ~30 shared locals + closures through module boundaries; risk unjustified; separate follow-up if file-size becomes a hard requirement). C — defer: rejected (the two functions are the file's main comprehension barrier).
- **Why chosen**: A delivers the substantive readability/maintainability dividend at bounded, coverage-gated risk, with public API untouched.
- **Consequences**: `run_dry_run` 499->~340L, `resolve_execution` 299->~60L, with 4-5 named helpers; `plan_execute.py` FILE size stays ~1,578 (helpers in-file — this is function decomposition, not file reduction). No behavior/signature change.
- **Follow-ups**: Option B (module extraction for file-size) only if required.

## Seam map
- `resolve_execution`: S1 `_resolve_snapshot_paths` (1040-1060, PURE) -> S3 `_resolve_finalize_approval` (1241-1312) -> S2 `_resolve_reject` (1071-1240, ~170L, **extracted LAST**, confirm pure-branch, split if separable sub-phases). Orchestrator becomes ~40L.
- `run_dry_run`: S4 `_build_dry_run_execution` (671-735, PURE dict build, LOW risk, FIRST) + S5 `_dry_run_record_and_dispatch` (755-804, relocate `_append`/`_mark_tasks` closures with it). Validation/isolation/agent-invocation stay inline.

## Sequencing (folds Architect R1)
1. Coverage pre-check gate (below). 2. PURE seams first: S4, S1. 3. S5, S3. 4. S2 (`_resolve_reject`) LAST, after confirming it is a pure branch; prefer 2 smaller helpers if it has separable sub-phases. Each helper = its own unit; `make test-fast` 1101/0 after each.

## Coverage pre-check gate (mandatory; Architect R2)
Per-named-branch coverage (NOT aggregate %): assert a test exercises each of reject / merge-conflict / approve / worktree / isolation-block / cancellation / pending-status. Add a characterization test for any uncovered target block BEFORE extracting it. Capture per-branch hit evidence as the QA artifact.

## Acceptance Criteria
- AC1: `run_dry_run` <= ~340L, `resolve_execution` <= ~60L; each helper <= ~120L; helpers `_`-prefixed, private, adjacent to caller (Architect R3).
- AC2: public signatures + return shapes identical — `inspect.signature(run_dry_run/resolve_execution)` matches pre-refactor.
- AC3: `make test-fast` 1101 passed / 0 failed + any added characterization tests pass.
- AC4: `mypy src/agent_lab` total == baseline (243); `ruff check` clean.
- AC5: move-only — each helper diff is a verbatim block lift (reviewer-confirmed).
- AC6: per-branch coverage report captured; no target block extracted without coverage.
- AC7: deliverable states scope = function decomposition; plan_execute.py file size ~unchanged (Option B is a separate follow-up).

## Pre-mortem (3, mitigated)
1. Mis-threaded local -> pure-seam-first, explicit params/returns, coverage oracle, per-helper green lane.
2. Lost early-return -> never extract early-return-to-outer; S2 is a value-returning branch, not a mid-function escape.
3. Broken closure capture -> relocate closures with their block (S5); never split a closure from captured scope.

## Test plan
Unit/integration (existing dry-run/resolve/merge tests + added characterization), e2e/smoke (signature probe + full fast lane + import smoke), observability (before/after function line counts + per-branch coverage; ruff/mypy delta 0).

## Recommended execution
ultragoal (per-helper green-lane + coverage gate fit goal-tracked verification). Pausable after any single helper (each lands green). Out of scope: Option B, any signature/logic/perf change.
