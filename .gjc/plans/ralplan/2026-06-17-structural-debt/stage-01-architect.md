# Architect Review — Structural Debt Decomposition (stage_n 1)

**Verdict: WATCH / COMMENT** — architecturally sound with the correct risk posture for load-bearing FSM/merge code; two real refinements required before final, neither a blocker.

## Steelman antithesis (strongest case AGAINST the chosen Option A)
Option A's "façade-preserving re-export" is, for *this* goal, partly self-defeating. The stated objective is **navigability** (smaller, easier-to-navigate modules for dogfooding). A re-export façade preserves the import *path* but splits a symbol's **declaration from its definition**: `go-to-definition` on `mission_loop.inject_wisdom_into_prompt` lands on a re-export line, not the implementation. Re-export façades accumulate and re-muddy the "which module owns this?" question the refactor is meant to answer. Option B (hard move + LSP-assisted rewire) yields the **honest import graph** where every import path reflects the true home. The plan dismisses B as "high churn," but for the *public* surface that churn is mostly mechanical and `lsp rename`/`references` is deterministic (it even resolves function-local lazy imports, which grep misses). The plan's own Cons for B ("grep-fragile") actually argue *for* using LSP rather than against migrating. So the antithesis: **A optimizes the transition cost; B optimizes the permanent end-state — and for a tool whose entire value is navigability, optimizing the end-state has a real claim.**

## Real tradeoff tensions
1. **Breakage-risk (favors A) vs. navigability-honesty (favors B).** Principle 2 (Public API immovable) + re-export collides with the project goal (more navigable modules). The plan logs this only as a minor con. It deserves an explicit default rule.
2. **Metric vs. substance — the giant functions survive.** `run_dry_run` (~500) + `resolve_execution` (~300) ≈ **800 of the 2,282 lines**, and they are the single hardest things to read/edit in the file. Option A explicitly leaves them in core ("shrink but stay monolithic"). After Phase 1, `plan_execute.py` hits the ≤900 AC1 target while ~800 of those lines are still two functions — **AC1 is satisfiable without materially reducing the real cognitive-load debt.** The "optional in-module sub-step" hand-waves the highest-value, highest-effort part.

## Synthesis (recommended adjustments — keep Option A's risk profile)
- **A1 — Migrate-by-default for small/countable external sites; re-export only for large/unknown.** The externally-imported movers are few and countable (notepad/wisdom ≈ 3 sites in `evidence_ledger.py` + `runtime/context.py`; `maybe_advance_mission`/`mission_autorun_enabled` ≈ 1 site in `mission_tick.py`; the `plan_execute` publics do **not** move — they stay in core, so zero issue there). Use `lsp rename`/`references` to migrate those ≤4 sites to the new module path. Reserve re-export for any case where the caller set is genuinely large or cannot be enumerated. This honors the navigability goal without raising risk (LSP catches lazy imports; full fast lane backstops).
- **A2 — Make the giant-function decomposition an honest, named scope boundary.** Either (a) add **Phase 3 — split `run_dry_run`/`resolve_execution` into private step-helpers within their module** with its own acceptance, or (b) explicitly state this plan delivers *module-level* extraction only and a *follow-up* plan owns *function-level* decomposition. Add an AC distinguishing "modules extracted" from "functions decomposed" so the line-count metric cannot be gamed.
- **A3 — Constant-ownership invariant (reinforce pre-mortem #2).** Make AC6 enforce exactly one definition site per moved constant, with a grep-proof in the QA artifact (e.g. `git grep -n 'PENDING_STATUS ='` returns one hit). Cheap, kills the silent-divergence class.

## Principle-violation flags (deliberate)
- **Principle 2 vs. project goal**: re-export-*by-default* mildly violates the spirit of "more navigable." → adopt A1 (migrate-by-default for small sites).
- **AC1 gameability**: a pure line-count AC can pass while the giant functions persist. → adopt A2 (separate the two scopes explicitly).

## What is already right (do not over-correct)
- Move-only + test-suite-as-oracle is the correct safety model for behavior-preserving refactors.
- Leaf-only extraction + function-local imports for back-references correctly matches the repo's dominant convention and forecloses the cycle risk.
- Phasing (plan_execute then mission_loop, green after each) is the right incremental, reversible shape.
- The risk posture (no hard-move of the *whole* surface; keep orchestrators in core) is appropriate for code that performs irreversible git merges.
