# Task 5 Gate Review

- recommendation: REJECT
- reviewed SHA: `4728ad6e9c70862142ab880a1c67431abdca1637`
- originalIntent: Keep TurnContract in shadow by default without changing supervisor behavior; record candidate/applied routing evidence and require a staged, human-approved promotion gate backed by clean, recent evidence.
- desiredOutcome: Outcome rows expose candidate/applied route, safety floor, topology, latency/cost, regret, and parity; roles/adaptive promotion only becomes metrics-green after 10 eligible sessions spanning 7 days, zero safety/under-routing failures, at least 99.5% parity, and no more than 10% p95 latency regression, while malformed/stale data cannot produce a successful report.
- userOutcomeReview: Default-shadow and focused regression behavior reproduce successfully, and the evidence schema covers the requested fields. The promotion report is not safe against stale or dirty ledger rows, so its success result can be misleading.

## Blockers

1. `violatedCriterion: T5-STALE-EXCLUDED`
   - Observation: Rows dated entirely in January 2020 are counted as 10 eligible sessions and produce `metrics_green=true` / `HUMAN_GO_REQUIRED`. The implementation has no freshness cutoff or evaluation timestamp; it only measures the span between the oldest and newest stage rows.
   - evidencePointer: `src/agent_lab/room/turn_contract_promotion.py:42`, `src/agent_lab/room/turn_contract_promotion.py:88`; reproduced command output `STALE_PROBE ... eligible_sessions: 10 ... metrics_green: True`.

2. `violatedCriterion: T5-MALFORMED-EXCLUDED`
   - Observation: Structurally accepted dirty rows can crash the report instead of being excluded and counted. A `float("nan")` latency raises `ValueError` in `_p95`; mixing an offset-naive ISO timestamp with normal aware timestamps raises `TypeError` during latest-row/window comparisons.
   - evidencePointer: `src/agent_lab/room/turn_contract_promotion.py:33`, `src/agent_lab/room/turn_contract_promotion.py:42`, `src/agent_lab/room/turn_contract_promotion.py:81`; reproduced outputs `nan_latency ValueError cannot convert float NaN to integer` and `naive_timestamp TypeError can't compare offset-naive and offset-aware datetimes`.

## Confirmed

- HEAD exactly equals requested SHA.
- `AGENT_LAB_TURN_CONTRACT_MODE` still defaults/falls back to `shadow` (`src/agent_lab/room/turn_contract.py:146`), covered by the reproduced focused suite.
- Reproduced targeted suite: `62 passed`.
- Reproduced routing regression suite: `86 passed`.
- Reproduced Task 5 Ruff scope: `All checks passed!`.
- Evidence projection includes candidate/applied IDs, safety floor, roster, rounds, consensus, latency, cumulative cost, regret, parity, and rollout mode.
- Gate constants and documented Human GO checkpoints match 10 sessions, 7 days, zero violations/critical under-routing, 99.5% parity, and 10% p95 regression.

## Direct programming / remove-ai-slops pass

- Production additions are scoped and contain no dead wrapper, speculative abstraction, prompt-text assertion, deletion-only test, or requested-removal tautology.
- Coverage weakness: the malformed-row test uses incomplete dictionaries only and labels them “stale”; it does not exercise genuinely stale-but-well-formed rows, non-finite numerics, or timezone-naive timestamps. This creates false confidence and directly contributes to both blockers.
- No separate Task 5 code-review report or manual QA matrix was present in the checked evidence directory. Direct artifact inspection and reproduction were performed instead.

## Checked artifacts

- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-5.md`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task5/baseline-targeted.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task5/targeted.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task5/routing-regression.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task5/ruff.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task5/manual-deterministic.json`
- `docs/TURN-CONTRACT.md`
- `scripts/turn_contract_promotion_report.py`
- `src/agent_lab/outcome_harvester.py`
- `src/agent_lab/room/turn_contract_evidence.py`
- `src/agent_lab/room/turn_contract_promotion.py`
- `tests/test_outcome_harvester_execute.py`
- `tests/test_turn_contract_promotion.py`

## Exact evidence gaps

- No test or deterministic artifact proves stale, well-formed evidence is excluded.
- No test or artifact proves non-finite latency and mixed timezone timestamps are safely excluded/countable as malformed.
- No Task 5-specific code-review report or manual QA matrix was found; this is noted but is not independently blocking because the direct pass reproduced the stated successful paths and found criterion-linked failures.
