# Dual-write retire Slice 3 — Execute/merge soft authority (M5)

> **작성:** 2026-07-14  
> **상태:** Implemented · profile default **on** · requires `DUAL_WRITE` · fail-closed after legacy side effects.  
> **선행:** Slice 1–2 soft authority · Full traffic soak PASS.  
> **관련:** [Slice 1](./dual-write-retire-slice-plan-soft-2026-07-14.md) · [Slice 2](./dual-write-retire-slice-inbox-soft-2026-07-14.md) · [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md)

## Slice definition

| Item | Value |
| --- | --- |
| Slice | **3 — Execute/merge/oracle soft authority** |
| Authority (when flag on) | Mission journal must record transitions (`StartExecution`→…→`RecordOracle`) |
| Side effects | Still legacy-first (`resolve_execution` / `confirm_merge` / `reverify`) |
| Fail-closed | HTTP **409** if approve/merge/oracle commit `mirrored≠true` |
| Reject | Still `legacy_only` (no Mission write) — not a 409 |
| Out of scope | Mission-first merge/Oracle side effects, M6 deletion, Oracle inventing PASS |

Also completed with this batch (Slice 2 leftovers):

| Leftover | Behavior |
| --- | --- |
| Supersede gate close | `supersede_pending_inbox` closes Mission gates when dual-write on |
| Harvest OpenExecutionGate | turn persist opens gates for harvested items (`sync_open_gates_for_inbox_items`) |

## Flags

| Flag | Default |
| --- | --- |
| `AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY` | **on** in balanced/thorough/autonomous |

## Rollback

Unset flag / set `0` → restart → fail-open `mirror_execution_transition` again.

## Dogfood checklist

- [x] API with `DUAL_WRITE=1` + execution/plan/inbox authority — 2026-07-14
- [x] `execution_approve_commit` mirrored (in-process after plan approve)
- [x] supersede pending → open_gates empty
- [x] Artifact: `/tmp/agent-lab-dw-execution-authority-20260714/reports/enable-smoke.json`