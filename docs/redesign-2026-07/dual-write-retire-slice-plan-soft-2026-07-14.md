# Dual-write retire Slice 1 — Plan decision soft authority (M4)

> **작성:** 2026-07-14  
> **상태:** **Human enable GO** on dogfood/production API (2026-07-14). Profile default **on** for balanced/thorough/autonomous (still requires `DUAL_WRITE`). M6 hard retire forbidden.  
> **선행:** Controlled cohort v3d GO · Full traffic soak PASS (≥15 turns) · pre-enable dogfood checks PASS.  
> **관련:** [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md) · [M4](./01-mission-kernel.md) · [full-traffic runbook](./dual-write-full-traffic-bounded-cutover-2026-07-14.md)

## Slice definition

| Item | Value |
| --- | --- |
| Slice | **1 — Plan decision soft authority** |
| Write authority (when flag on) | Mission journal (`ApprovePlan` / `RejectPlan`) |
| Compatibility projection | `run.json` `plan_workflow.phase` via `_project_plan` |
| Side effects (legacy) | verified_loop / session_goal / mission_loop / orchestration stamps |
| Consumers | Still read `plan_workflow` (execute gate, UI) — **no journal-first reads** |
| Out of scope | execute/merge/Oracle writers, inbox authority, M6 deletion |

```text
Flag ON (authority):
  HUMAN_PENDING gate
    → Mission commit (journal + project phase)
    → legacy side effects only (skip phase re-write)

Flag OFF (rollback):
  approve_plan / reject_plan (legacy phase write)
    → mirror_plan_* (dual-write)
```

## Flags

| Flag | Role | Default | Dogfood API (2026-07-14) |
| --- | --- | --- | --- |
| `AGENT_LAB_MISSION_DUAL_WRITE` | Bridge / cohort gate | off | **on** |
| `AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS` | Optional session allowlist | empty = all when dual-write on | empty |
| `AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY` | Soft retire Slice 1 | **on** (balanced/thorough/autonomous profile) | **on** |

`plan_write_authority_enabled(folder)` requires **both** `PLAN_WRITE_AUTHORITY` and `dual_write_enabled(folder)`. Authority without dual-write is a hard no.

## Enable record (Human 2026-07-14)

- Process: `uvicorn :8765`
- Env: `AGENT_LAB_MISSION_DUAL_WRITE=1` + `AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY=1` (`env -u …_SESSIONS`)
- Live smoke PASS: approve → `plan_approve_commit` / `APPROVED` / `PlanApproved`; reject `REFINE` → `plan_reject_commit`
- Artifact: `/tmp/agent-lab-dw-plan-authority-20260714/` (`enable-meta.txt`, `reports/enable-smoke.json`)

## Rollback

1. Unset / set `AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY=0` (or omit). Keep or drop `DUAL_WRITE` as needed.
2. Restart API process.
3. Path reverts to legacy-first + `mirror_plan_*`. No irreversible cleanup in this slice.

Do **not** delete writers or dual-write bridges as part of rollback.

## Dogfood checklist (before / at enable)

- [x] Dedicated process: `DUAL_WRITE=1` + `PLAN_WRITE_AUTHORITY=1` (allowlist empty for full dogfood traffic).
- [x] Plan approve → `plan_workflow.phase=APPROVED`, journal has `PlanApproved`, execute gate passes.
- [x] Plan reject `target_phase=REFINE` → projected `REFINE` (authority path).
- [x] Double approve after APPROVED → blocked (Human gate preserved).
- [x] Pre-enable isolated dogfood + rollback check PASS (2026-07-14).
- [x] Human enable GO recorded in ADR-001 / NOW.
- [x] Daily dogfood on live `:8765` PASS (2026-07-14): approve commit / reject REFINE / double-approve 409 / verify hard_mm=0 — `/tmp/agent-lab-dw-plan-authority-20260714/reports/daily-dogfood.json`.

## Success criteria for this slice

- Implementation + process enable on dogfood API.
- Profile defaults do **not** ship `DUAL_WRITE` as applied flags; `PLAN_WRITE_AUTHORITY` defaults **on** for balanced/thorough/autonomous (no-op unless dual-write is also on).
- Legacy writers retained until M6 Human approval.

## Later slices (documented only)

| Slice | Topic | Human gate |
| --- | --- | --- |
| 2 | Execution-gate inbox soft authority | [slice-2 runbook](./dual-write-retire-slice-inbox-soft-2026-07-14.md) |
| 3 | Execute/resolve · merge/confirm soft authority (M5) | Yes |
| 4 | Hard retire: delete dual-write + legacy lifecycle writers (M6) | Yes — irreversible cleanup scope |
