# Architect Review — Phase 3 Giant-Function Decomposition (stage_n 1)

**Verdict: CLEAR / APPROVE** — the risk posture is correct for irreversible-merge code; one sequencing refinement and one coverage-precision note, neither a blocker.

## What is right
- The AC1 file-size-vs-function-size correction is the key honesty fix: it removes the gameable metric and names the real debt (two unreadable functions). De-scoping Option B (module extraction with ~30-local threading on git/merge code) is the correct call — that risk is not justified by a file-size number.
- Pure-seam-first + "relocate closures with their block" + "never extract early-return-to-outer" are exactly the invariants that keep extract-method behavior-preserving. Pre-mortem maps the three real failure modes (mis-threaded local, lost early-return, broken closure capture) to concrete mitigations.
- AC2's `inspect.signature` probe is a real, cheap guard that the public contract is untouched.

## Steelman antithesis (considered, rejected)
One could argue Phase 3 should be skipped entirely (Option C): the functions work, tests pass, and extract-method on merge code is pure downside risk. Rebuttal: the two functions are the single largest comprehension barrier in the file; every future edit to dry-run/resolve pays the 300-500-line read tax, and that tax is itself a correctness risk. Conservative pure-seam extraction converts the unreadable pipeline into a named, testable sequence with no behavior change — the readability dividend outweighs the bounded, coverage-gated risk.

## Refinements (fold into final)
- **R1 — sequence S2 (`_resolve_reject`, ~170L) LAST.** It is the largest and most stateful extraction. Land the PURE seams first (S1 snapshot-paths, S4 execution-dict builder) to prove the pipeline and the per-helper green-lane discipline; extract S2 only after, and first confirm it is a *pure branch* (the `if vote=="reject":` block ends by producing the result the orchestrator returns — no `return` that escapes from a deeper nesting level mid-block). If S2 contains independent sub-phases (worktree-discard vs task-revert vs status-set), prefer two smaller helpers over one 170-line move.
- **R2 — branch-specific coverage, not aggregate %.** The coverage gate must assert each *named target block* is executed by a test (reject/merge-conflict/approve/worktree/block/cancellation), not merely that file-level coverage is high. Capture per-branch hit evidence in the QA artifact.
- **R3 — locality + privacy.** New helpers are `_`-prefixed and placed immediately adjacent to their single caller (no new public surface, no cross-file move). This keeps `go-to-definition` one scroll away and avoids implying reuse that does not exist.

## Status
CLEAR. Architecturally approvable as conservative, coverage-gated, behavior-preserving extract-method. Defer to Critic.
