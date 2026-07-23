# Task 5 — TurnContract shadow evidence and promotion gate

## Binary observables

| Scenario | Invocation | Observable | Artifact |
|---|---|---|---|
| Baseline routing/runtime/inbox | `.venv/bin/pytest tests/test_turn_contract.py tests/test_turn_contract_runtime.py tests/test_runtime_snapshot.py tests/test_fast_inbox_skip.py -q` | `44 passed` | `task5/baseline-targeted.log` |
| Shadow ledger + report gate | `PYTHONPATH=src .venv/bin/pytest tests/test_turn_contract.py tests/test_turn_contract_runtime.py tests/test_runtime_snapshot.py tests/test_outcome_harvester_execute.py tests/test_fast_inbox_skip.py tests/test_turn_contract_promotion.py -q` | `62 passed` | `task5/targeted.log` |
| Routing regression | `PYTHONPATH=src .venv/bin/pytest tests/test_turn_policy.py tests/test_eval_surface_graders.py -q` | `86 passed` | `task5/routing-regression.log` |
| Lint | `PYTHONPATH=src .venv/bin/ruff check <Task5 paths>` | `All checks passed!` | `task5/ruff.log` |
| Safe high-risk floor | deterministic direct Python invocation of `build_turn_contract_evidence` | applied=`critical_review`, `safety_floor_satisfied=true`, parity=`true` | `task5/manual-deterministic.json` |
| Insufficient promotion history | same invocation with nine distinct `roles` sessions across seven days | decision=`BLOCK`, reason=`eligible_sessions<10`, violations=`0` | `task5/manual-deterministic.json` |
| Stale verifier probe | direct report invocation with ten `roles` rows from 2020 | eligible=`0`, stale=`10`, decision=`BLOCK` | `task5/verifier-manual.json` |
| Malformed verifier probe | direct report invocation with one `NaN` latency and one timezone-naive timestamp | eligible=`8`, malformed=`2`, decision=`BLOCK` | `task5/verifier-manual.json` |
| Verifier repair regression | `PYTHONPATH=src .venv/bin/pytest tests/test_turn_contract_promotion.py tests/test_outcome_harvester_execute.py tests/test_turn_contract.py tests/test_turn_contract_runtime.py tests/test_fast_inbox_skip.py -q` | `55 passed` | `task5/verifier-targeted.log` |
| CLI fail-closed surface | `PYTHONPATH=src .venv/bin/pytest tests/test_turn_contract_promotion.py::test_promotion_cli_emits_machine_readable_gate -q` | `1 passed`, subprocess exit=`2`, JSON decision=`BLOCK` | `task5/verifier-cli.log` |

## Gate and invariants

- `roles`, then `adaptive`: each requires 10 eligible sessions, a 7-day window, zero safety-floor violations, zero critical under-routing, parity at least 99.5%, and p95 latency regression at most 10%.
- A green result returns `HUMAN_GO_REQUIRED`; it never changes the runtime mode.
- `AGENT_LAB_TURN_CONTRACT_MODE` remains default `shadow`; supervisor implicit behavior is covered by the unchanged routing/runtime/inbox suites.
- Route regret, candidate/applied route, safety outcome, roster/round/consensus, latency, and cumulative session cost are recorded on outcome ledger rows.

## Adversarial coverage

- stale/malformed data: excluded from eligibility and counted by the report.
- misleading success: a metrics-green stage still requires Human GO.
- unsafe under-route: recorded as floor violation and parity failure, then blocks promotion.
- flaky repeat: deterministic fixture/test runs contain no time or random dependency.
- destructive operations, network faults, process restart, and Mission authority: N/A to this read-only report and outcome projection.
- temporary resources: none retained.
