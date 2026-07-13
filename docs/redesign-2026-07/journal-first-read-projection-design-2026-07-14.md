# Journal-first read / inbox·mission_loop projection design

> **작성:** 2026-07-14  
> **상태:** Wave A shipping (read-model composites). Wave B / M6 **별도 Human gate**.  
> **선행:** Soft slices 1–3 · [m6-precheck](./m6-precheck-retire-scope-2026-07-14.md)  
> **관련:** [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md) · [`mission/read_model.py`](../../src/agent_lab/mission/read_model.py)

## Decision lock

- Production UI/gates still read **`run.json`** until explicitly cut over.
- Full **`human_inbox` rows** remain the UI payload (forever-projection). Mission **gates** = wait-state authority only; read-model joins `gate_id` → row.
- **`mission_loop` is not cloned into the journal.** Wave A exposes `operational_status` + thin overview from Mission. Wave B may project a thin status subset into `run.json`.
- **Out of scope here:** M6 writer deletion, objection BLOCK, execute/merge/Oracle implementer moves.

## Three layers

```text
(A) Journal SSOT          (B) Compatibility projection     (C) Journal-first API
mission-events.jsonl      run.json fields UI/gates use     GET /mission/read-model
+ plan.md (+ Decision*)   plan_workflow / human_inbox      composites for future UI
```

| Layer | Role | Status |
| --- | --- | --- |
| A | Write authority (soft slices 1–3) | Shipping |
| B | Keep gates/UI alive without journal-first consumers | Plan via `_project_plan`; inbox rows still written; no mission_loop projector yet |
| C | One preferred read contract | Wave A enriches API; web flag default **off** |

## Layer A — facts explainable from journal

- Mission state, plan hashes/revision, repairs, oracle, `open_gates`, `event_cursor`
- Execution/merge/Oracle lifecycle events (Slice 3)
- Inbox **wait** = gates; inbox **content** = `human_inbox` row where `id == gate_id` until Decision store owns copy

## Layer B — compatibility projections

| Surface | Projector | Wave |
| --- | --- | --- |
| `plan_workflow.phase` (+ hash) | `_project_plan` | Done |
| `human_inbox[]` | Create/resolve/harvest still write rows; **row write = decision surface projection, not rival lifecycle authority** | Doc + current code |
| `mission_loop` thin | `_project_mission_loop_status` (phase/pause/circuit-shaped) | **Wave B** |
| `work_phase` | Mapped on read-model from Mission status (Wave A); optional `run.json` stamp later | Wave A API |

## Layer C — Wave A read-model composites

`GET /api/sessions/{id}/mission/read-model` gains (non-breaking add):

| Field | Source |
| --- | --- |
| `plan` | Mission hashes + `plan_workflow` join → `{phase, hash, approved_hash, pending_approval}` |
| `work_phase` | Map from `MissionState` / `operational_status` (see table below) |
| `mission_overview` | `{phase_label, paused, circuit_breaker, pending_inbox_count}` |
| `inbox_summary` | Gates ∪ legacy pending counts `{pending_count, pending_questions, pending_builds}` |
| `inbox_items` | `[]` until Wave B join |

### `work_phase` map (Wave A)

| Operational / state signal | `work_phase` |
| --- | --- |
| COMPLETED / SUCCEEDED | `done` |
| FAILED / CANCELLED | `done` |
| WAITING + `AWAITING_DIFF_DECISION` or open gates mid-exec | `review_needed` |
| WAITING + `AWAITING_PLAN_DECISION` / `AWAITING_HUMAN` | `plan_draft` or `review_needed` (plan wait → `plan_draft`) |
| RUNNING + VERIFYING/REPAIRING | `merge_verify` |
| RUNNING + EXECUTING / READY | `execute_pending` |
| PLANNING / DRAFTING | `plan_draft` |

### Unmigrated sessions

Legacy payload fills `plan` / `work_phase` / `mission_overview` / `inbox_summary` from `run.json` only; `operational_status` stays null; `source=legacy`.

## Wave B (later)

1. `_project_mission_loop_status` after Mission transitions.
2. `inbox_items` = join open gates + `human_inbox` rows (`HumanInboxItem` shape).
3. UI flag `AGENT_LAB_MISSION_UI_READ_MODEL=1` to prefer read-model for overview/inbox.
4. Then reconsider M6 (still separate Human approval).

## M6 unlock criteria

- Execute gate OK on projected `plan_workflow` **or** journal-first gate helper.
- Inbox UI dogfood on join/read-model without missing prompt/options.
- Work status/overview dogfood without raw `mission_loop` as SSOT.
- Explicit Human approval for irreversible deletion.

## Flags

| Flag | Default | Role |
| --- | --- | --- |
| `AGENT_LAB_MISSION_UI_READ_MODEL` | **off** | Web may fetch read-model; must not replace Composer/Inbox until Wave B |

## Non-goals

- Deleting `approve_plan` / `create_inbox_item` / `mission/loop.py` writers
- Cloning full `mission_loop` action queues into journal
- Auto-reconcile competing lifecycle writers
