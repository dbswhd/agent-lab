# Critic Evaluation — Structural Debt Decomposition (stage_n 2, re-review of revision)

**Verdict: APPROVE** — all three stage_n-1 gating fixes are correctly incorporated; ACs are now non-gameable and verification is concrete. One execution gate (from Architect pass 2) is attached as an APPROVE condition for Phase 3.

## Gating-fix verification
1. **AC1 gameability -> RESOLVED.** Phase 3 now explicitly owns giant-function decomposition (private step-helpers, no public-signature change); AC8 forbids claiming Phase 3 from a line-count pass. Scope is honest and the metric cannot be gamed.
2. **Re-export default -> RESOLVED.** Migrate-by-default with a named site table (`evidence_ledger.py`, `runtime/context.py`, `mission_tick.py`) and `lsp references` pre-flight; re-export reserved for large/unenumerable sets. Execution is unambiguous.
3. **Constant ownership -> RESOLVED.** AC6 is proof-bearing with concrete `git grep` single-definition invariants per constant.

## Quality gates (all pass)
- Principle ↔ option consistency: PASS (unchanged, still coherent).
- Fair alternatives: PASS.
- Risk-mitigation clarity: PASS — cycle (leaf-only + local imports + AC7), private-importer (lsp references + full lane), constant-divergence (AC6 grep-proof) all closed.
- Testable acceptance criteria: PASS — AC2 import probe updated for migrated homes; AC4/AC5 name exact commands; AC8 discriminates scope; AC6 carries proof.
- Concrete verification steps: PASS — per-extraction green-lane checkpoints + copy-pasteable probes.
- Pre-mortem + expanded test plan (deliberate gates): PASS (carried from stage_n 1, still adequate).

## APPROVE condition (execution gate for Phase 3 — from Architect pass 2)
Phase 3 (splitting `run_dry_run`/`resolve_execution`) is the highest-risk phase: extract-method across mutable locals, early returns, and git/merge control flow has no compile-time signal for a mis-thread. Therefore Phase 3 MUST:
- run only after Phases 1–2 are green;
- **before extracting, confirm branch coverage** of the two giants (dry-run, resolve, merge-conflict, paths-outside-expected, verify-retry); add a characterization test first where a branch is uncovered, so the extract-method has a real oracle;
- proceed one step-helper at a time, each a move-only diff, with the public body reduced to ordered calls preserving identical control flow.
This is an execution discipline, not a plan change; Phases 1–2 are unconditionally approved and shippable on their own.

## Decision
APPROVE. Ready to mark `pending approval` and persist the ADR/final plan. Recommended execution path: ultragoal (goal-tracked, verification-gated) given the move-only + per-phase green-lane discipline; team only if interactive tmux parallelization is wanted (not required here).
