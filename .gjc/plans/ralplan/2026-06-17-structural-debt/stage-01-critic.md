# Critic Evaluation — Structural Debt Decomposition (stage_n 1)

**Verdict: ITERATE** — high-quality, near-approvable plan; three concrete gating fixes (all align with the Architect's A1/A2/A3) must be folded in, after which it is APPROVE-able. Not a REJECT: scope, options, and verification framework are sound.

## Quality assessment (passes)
- **Principle ↔ option consistency**: PASS. Principles (move-only, public-API-immovable, convention-reuse, leaf-only/no-cycles, incremental) directly justify Option A; no contradiction.
- **Fair alternatives**: PASS. B and C are steelmanned, not strawmanned (B's clean end-state and C's zero-risk are stated honestly). The Architect even surfaced B's genuine upside.
- **Pre-mortem quality** (deliberate gate): PASS. Three concrete failure modes (cycle, constant divergence, private-symbol importers) each with a mapped mitigation and a backstop (AC7/full lane).
- **Expanded test plan** (deliberate gate): PASS. Unit/integration/e2e-smoke/observability all covered; the existing suite is correctly named as the behavioral oracle for a move-only change.
- **Testable ACs**: MOSTLY PASS. AC2/AC3/AC4/AC5/AC7 have executable probes. AC1/AC6 are the weak spots (below).

## Gating fixes required before APPROVE
1. **AC1 is gameable — separate "module extracted" from "function decomposed" (Architect A2).** `run_dry_run` (~500) + `resolve_execution` (~300) ≈ 800 of 2,282 lines. A pure "≤900 lines" AC can pass while those two functions persist intact, leaving the dominant cognitive-load debt untouched. Fix: either add **Phase 3** (split the two giants into private step-helpers *within* their module, with its own acceptance + green lane) OR explicitly scope this plan to *module-level* extraction and register *function-level* decomposition as a named follow-up. Add an AC that states which of the two is delivered, so the metric cannot be gamed.
2. **Re-export-by-default contradicts the navigability goal — migrate-by-default for countable sites (Architect A1).** Enumerate the exact external movers (notepad/wisdom: `evidence_ledger.py`, `runtime/context.py`; advance: `mission_tick.py`) and migrate those ≤4 sites to the new module path via `lsp rename`/`references`. Reserve re-export only for large/unenumerable caller sets. Plan must list the sites by name so execution is unambiguous.
3. **Constant single-ownership must be proof-bearing (Architect A3).** Strengthen AC6: each moved constant (`PENDING_STATUS`, `_CANCELLABLE_EXECUTION_STATUSES`, `MISSION_WISDOM_INJECT_CAP`, `MISSION_NOTEPAD_FILES`, etc.) must have exactly one definition home, verified by a grep-proof captured in the QA artifact (e.g. `git grep -n 'PENDING_STATUS = '` returns one hit; re-export lines reference, not redefine).

## Risk-mitigation clarity
- Adequate for the cycle and private-importer risks (LSP references + import smoke + full lane). The constant-divergence risk needs the AC6 proof above to be fully closed.

## Verification concreteness
- Strong: AC2 import probe and AC3 app-boot are copy-pasteable; AC4 names the exact `make test-fast` lane and the known-excluded pre-existing failures. Add per-extraction "green lane" checkpoints to the sequencing (already implied) and the AC6 grep-proof.

## Required for APPROVE
Fold fixes 1–3 into a revised plan (Phase 3 or explicit scope split for the giants; named migrate sites; proof-bearing AC6). Re-review (Architect + Critic) then APPROVE expected.
