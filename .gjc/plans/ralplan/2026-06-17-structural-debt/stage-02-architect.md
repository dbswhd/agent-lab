# Architect Review — Structural Debt Decomposition (stage_n 2, re-review of revision)

**Verdict: CLEAR / APPROVE** — the revision correctly incorporates A1/A2/A3. The approach is architecturally sound and the scope is now honest. One execution-time guardrail noted (not a plan defect).

## Refinement verification
- **A1 (migrate-by-default)**: RESOLVED. The revision enumerates the exact external movers in a table (`evidence_ledger.py`, `runtime/context.py`, `mission_tick.py`) and commits to `lsp rename`/`references` migration, reserving re-export only for large/unenumerable caller sets, with an `lsp references` pre-flight to decide. This yields the honest import graph without raising risk. Correct.
- **A2 (honest scope)**: RESOLVED. Phase 3 now explicitly owns the giant-function decomposition as *private step-helpers within the module* (no public-signature change), is independently shippable/deferrable, and AC8 forbids claiming Phase 3 from a line-count pass alone. The metric can no longer be gamed. Correct.
- **A3 (constant ownership)**: RESOLVED. AC6 is now proof-bearing with concrete `git grep` invariants per constant. Correct.

## One execution-time guardrail (WATCH, not a blocker)
**Phase 3 is the highest-risk phase and must be sequenced last with the tightest review.** Extract-method on `run_dry_run` (~500) and `resolve_execution` (~300) is *not* a trivial code-move: these functions carry mutable locals, early returns, and exception/merge-control flow across git operations. A step-helper that mis-threads a mutated local or swallows an early-return path is a silent behavior bug with no compile-time signal. Therefore:
- Phase 3 runs only after Phases 1–2 are green (already specified).
- **Before splitting, confirm the two giants have adequate behavioral coverage** (the dry-run / resolve-execution / merge tests). If coverage of a branch (e.g. merge-conflict, paths-outside-expected, verify-retry) is thin, add a characterization test *first* so the extract-method has a real oracle — `make test-fast` green is only as strong as the coverage of those branches.
- Each step-helper extraction is its own move-only diff; the public function body must reduce to ordered calls + the same control flow.
This is consistent with the plan's move-only principle and AC4; it sharpens *where* the risk concentrates. It does not require a plan change — recommend the Critic note it as an execution gate for Phase 3.

## Tradeoff resolution
The earlier breakage-risk vs. navigability-honesty tension is now resolved in favor of honesty for the countable surface (migrate) while keeping the low-risk posture for the orchestrators (stay in core). The metric-vs-substance tension is resolved by separating Phases 1–2 (extraction) from Phase 3 (decomposition) with AC8. Both prior antitheses are answered.

## Status
CLEAR. Architecturally approvable. Defer to Critic for final quality sign-off; the only addition is the Phase-3 coverage/sequencing gate above.
