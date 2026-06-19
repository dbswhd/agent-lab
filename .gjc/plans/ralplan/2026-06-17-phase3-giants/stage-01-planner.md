# Planner — Phase 3: Giant-Function Decomposition (`run_dry_run`, `resolve_execution`)

## Context (measured, post Phase 1/2)
- `plan_execute.py` = 1,578 lines. The two giants dominate cognitive load:
  - `run_dry_run` (lines 318-816, **499 lines**) — sequential pipeline with shared mutable locals, early returns, and 5 inner closures (`_record_blocked`, `_on_activity`, `_append`, `_mark_tasks`, `_sync_board`).
  - `resolve_execution` (lines 1014-1312, **299 lines**) — setup + a ~170-line `reject` branch (1071-1240) + approve/finalize tail.
- Phases 1/2 (module extraction) are merged-green: fast lane 1101/0, mypy 243==baseline, ruff clean.

## Critical framing correction (vs earlier AC1)
**In-module function decomposition reduces FUNCTION size (the real "God function" pain), NOT file size** — extracted private helpers live in the same `plan_execute.py`, so the file stays ~1,578. The earlier AC1 "plan_execute.py <= ~900" conflated file-size with function-size. Achieving a <=900 *file* requires moving the giants' logic into a NEW module, which is materially higher risk (mid-function blocks thread ~30 shared locals + closures). This plan optimizes the substantive debt — the two unreadable functions — not the file-size metric.

## Principles
1. **Extract-method only, behavior-preserving.** No logic change; each helper is a verbatim block lifted into a named function with explicit params/returns. Public signatures of `run_dry_run`/`resolve_execution` are UNCHANGED.
2. **Pure-seam-first.** Extract only well-bounded blocks (clear inputs, single output, no early-return-to-outer, no closure capture). Leave high-coupling blocks (the 5 closures, early-return validation) in place.
3. **Coverage is the oracle.** Extract-method has no compile-time signal for a mis-threaded local; the existing tests are the only safety net, so branch coverage must be confirmed/added BEFORE extracting.
4. **One helper at a time, green after each.** Each extraction is its own commit-sized unit; `make test-fast` 1101/0 after each.

## Decision Drivers
1. Extract-method risk on load-bearing git/merge code (shared locals, early returns, closures) — favors conservative pure-seam-only.
2. Branch-coverage of dry-run/resolve paths is the only behavioral oracle — gate on it.
3. The win = each giant becomes a short orchestration body + named, independently-readable step-helpers.

## Options
- **A — Conservative in-module pure-seam extraction (RECOMMENDED).** Extract the cleanly-bounded blocks into private helpers within `plan_execute.py`; leave closures and early-return validation inline. Giants shrink to readable orchestrators; file size ~unchanged. Lowest risk; directly fixes the function-level debt.
- **B — Module extraction of the giants' logic** into `plan_execute_dryrun.py`/`plan_execute_resolve.py` to also cut file size <=900. Higher risk: mid-function blocks thread ~30 locals + closures; back-ref injection explodes. Reserve as a separate follow-up only if file-size is a hard requirement.
- **C — Defer.** Zero risk; the two unreadable functions remain. Rejected (the user explicitly wants Phase 3 planned).

**Chosen: A.** Delivers the real readability/maintainability win at acceptable risk; B's file-size gain does not justify its state-threading risk on irreversible-merge code.

## Concrete seam map (Option A)
### `resolve_execution`
- S1 `_resolve_snapshot_paths(target) -> tuple[list,list,list,list,str]` ← lines 1040-1060 (snapshot/source/artifact path reconstruction). PURE, low risk. ~20L.
- S2 `_resolve_reject(folder, target, *, snapshot ctx, completed) -> dict` ← the ~170-line reject branch 1071-1240. Self-contained branch (worktree discard, task revert, status set). MEDIUM risk; highest value. Returns the result dict; `resolve_execution` returns it directly when `vote=="reject"`.
- S3 `_resolve_finalize_approval(folder, target, *, auto_meta, completed) -> dict` ← 1241-1312 (approval record, `_update`, task-complete, plan advance). MEDIUM. The `_update` closure stays inside S3.
- Result: `resolve_execution` becomes ~40 lines: validate vote/target/status -> S1 -> branch to S2 (reject) or S3 (approve).

### `run_dry_run`
- S4 `_build_dry_run_execution(*, action, exec_id, cwd, diff, diff_stat, touched, outside, verification_artifacts, worktree ctx, ...) -> dict` ← the execution-dict assembly 671-735 (~64L). PURE construction from locals, no control flow. LOW risk; high value.
- S5 `_dry_run_record_and_dispatch(folder, execution, action) -> None` ← persist tail 755-804 (`_append`/`_mark_tasks` closures move inside, evidence sync, dispatch). MEDIUM. The two closures relocate with it.
- Leave inline: validation/load (early returns), isolation/worktree setup (`_record_blocked` closure + early return), agent-invocation try (`_on_activity` closure + cancellation). These are high-coupling; extracting them is Option-B territory.
- Result: `run_dry_run` shrinks from 499 to ~330 readable lines with two named helpers.

## Coverage pre-check gate (mandatory, before any extraction)
Run focused coverage on the dry-run/resolve branches and confirm each target block is exercised:
- dry-run: worktree path, isolation block, snapshot-existed guards, cancellation, diff-safety, adversarial, pending-status return.
- resolve: reject branch (merge-conflict + plain), approve branch, task-complete, plan-advance, snapshot-path reconstruction.
Add a characterization test for any uncovered target block FIRST. Source: `tests/test_plan_execute*.py`, `test_plan_execute_revise_api.py`, `test_mission_loop_e2e.py`, merge/resolve tests.

## Acceptance Criteria
- AC1 (function size): `run_dry_run` <= ~340 lines, `resolve_execution` <= ~60 lines; each new helper <= ~120 lines.
- AC2 (public API unchanged): `run_dry_run`/`resolve_execution` signatures + return shapes identical; `python -c "import inspect, agent_lab.plan_execute as p; print(inspect.signature(p.run_dry_run), inspect.signature(p.resolve_execution))"` matches pre-refactor.
- AC3: `make test-fast` 1101 passed / 0 failed (baseline); plus any added characterization tests pass.
- AC4: `mypy src/agent_lab` total unchanged vs baseline (243); `ruff check` clean.
- AC5 (move-only): each helper diff is a verbatim block lift; reviewer confirms no logic/constant change.
- AC6 (coverage): the coverage pre-check report is captured as a QA artifact; no target block extracted without coverage.
- AC7 (no file-size claim): the deliverable states Phase 3 = function-level decomposition; plan_execute.py file size is ~unchanged (Option B is a separate follow-up).

## Pre-mortem (3)
1. **Mis-threaded local on extraction** (a helper reads/writes a local that the orchestrator also mutates) -> silent wrong behavior. Mitigation: pure-seam-first (single output, no shared mutation); explicit params/returns; coverage oracle; per-helper green lane.
2. **Early-return semantics lost** (extracting a block that early-returns from the outer function). Mitigation: do NOT extract early-return blocks (S2 returns a value the orchestrator returns; it is a branch, not a mid-function escape); leave validation/isolation inline.
3. **Closure capture broken** (moving a closure changes what it captures). Mitigation: relocate closures WITH their block (S5 keeps `_append`/`_mark_tasks` inside); never split a closure from its captured scope.

## Expanded test plan
- Unit/integration: existing plan_execute dry-run/resolve/merge tests as the oracle; add characterization tests per the coverage gate.
- e2e/smoke: signature probe (AC2), full `make test-fast`, import smoke.
- Observability: before/after function line counts + coverage report in the deliverable; ruff/mypy delta 0.

## Out of scope
- Option B (module extraction / file-size <=900) — separate higher-risk follow-up.
- Any signature, logic, or performance change.
