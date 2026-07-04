# F8 — Cost / credit visibility (quarterly)

> Status: **instrumented** · NORTH-STAR F8 · session ledger already exists; this adds **cross-session quarter rollup** + optional autonomy demotion

## Goal

Make LLM spend visible beyond a single mission, and optionally **demote autonomy (→ L0)** when a quarterly USD cap is exceeded — financial reading of §2.3 principle 1.

## Layers

| Layer | Store | Cap flag |
|-------|--------|----------|
| Session | `run.json` → `cost_ledger` | `AGENT_LAB_MISSION_BUDGET_USD` |
| Quarter | `.agent-lab/cost_ledger_quarter.json` | `AGENT_LAB_QUARTER_BUDGET_USD` |

Session spend is rolled up on every `persist_cost_ledger` (agent turn boundary).

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `AGENT_LAB_QUARTER_BUDGET_USD` | unset | Quarterly USD ceiling (empty = track only) |
| `AGENT_LAB_QUARTER_BUDGET_WARN_PCT` | `80` | Warn threshold |
| `AGENT_LAB_QUARTER_BUDGET_DEMOTE` | on when cap set | Demote autonomy ceiling to **L0** when over |

```bash
export AGENT_LAB_QUARTER_BUDGET_USD=50
# optional:
export AGENT_LAB_QUARTER_BUDGET_WARN_PCT=80
export AGENT_LAB_QUARTER_BUDGET_DEMOTE=1
make dev
```

## Report

```bash
make f8-cost-report
make f8-cost-report JSON=1
```

Runtime snapshot also exposes `cost_quarter` on `GET /api/sessions/{id}/runtime`.

## Autonomy demotion

When `over` and demote enabled, `record_autonomy_transition(..., to_level="L0", trigger="demotion", reason="quarter_budget_over:YYYY-Qn")` runs after ledger persist. Human can raise the ceiling again via Autonomy dial / inbox restore (N4 v2).

## Decision (optional ops note)

| Field | Value |
|-------|--------|
| Quarter | e.g. 2026-Q3 |
| Cap USD | |
| Policy | track-only / demote-on-over |

## Code SSOT

| Piece | Path |
|-------|------|
| Session ledger | `cost_ledger.py` |
| Quarter rollup | `cost_ledger_quarter.py` |
| Report | `scripts/f8_cost_report.py` |
| Runtime | `runtime/snapshot.py` → `cost_quarter` |
