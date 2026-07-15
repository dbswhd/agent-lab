# Dual-write retire Slice 3 — Execute/merge soft authority (M5)

> **작성:** 2026-07-14  
> **상태:** **Historical evidence / retired (2026-07-14; non-runtime).** The Slice 3 authority function is now disabled/fail-closed and its environment variable is ignored. The recorded legacy-first/fail-closed behavior remains below for audit.
> **현재 런타임:** The dual-write bridge requires a non-empty session allowlist; an empty allowlist disables it. This document's enable commands and profile-default claims are historical only.
> **선행:** Slice 1–2 soft authority · Full traffic soak PASS.  
> **관련:** [Slice 1](./dual-write-retire-slice-plan-soft-2026-07-14.md) · [Slice 2](./dual-write-retire-slice-inbox-soft-2026-07-14.md) · [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md)

## Historical slice definition (non-runtime evidence)

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

## Historical flags (non-runtime evidence)

| Flag | Default |
| --- | --- |
| `AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY` | **Retired** authority flag (ignored; disabled/fail-closed) |

## Historical rollback record (non-runtime evidence)

Unset flag / set `0` → restart → fail-open `mirror_execution_transition` again.

## Historical dogfood checklist (non-runtime evidence)

- [x] Historical API run with `DUAL_WRITE=1` + execution/plan/inbox authority — 2026-07-14; authority flags are now ignored.
- [x] `execution_approve_commit` mirrored (in-process after plan approve)
- [x] supersede pending → open_gates empty
- [x] Artifact: `/tmp/agent-lab-dw-execution-authority-20260714/reports/enable-smoke.json`
