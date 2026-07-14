# Dual-write retire Slice 2 — Inbox execution-gate soft authority

> **작성:** 2026-07-14  
> **상태:** **Historical evidence / retired (2026-07-14; non-runtime).** The Slice 2 authority function is now disabled/fail-closed and its environment variable is ignored. Supersede gate close + harvest OpenExecutionGate evidence remains below for audit.
> **현재 런타임:** The dual-write bridge requires a non-empty session allowlist; an empty allowlist disables it. This document's enable commands are historical only.
> **선행:** Slice 1 plan soft authority enable GO · Full traffic soak PASS.  
> **관련:** [Slice 1 plan](./dual-write-retire-slice-plan-soft-2026-07-14.md) · [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md) · [execution-gate design](./execution-gate-design-draft-2026-07-13.md)

## Historical slice definition (non-runtime evidence)

| Item | Value |
| --- | --- |
| Slice | **2 — Inbox execution-gate soft authority** |
| Write authority (when flag on) | Mission journal (`OpenExecutionGate` / `CloseExecutionGate`) |
| Compatibility projection | `run.json` `human_inbox` / `inbox_pending` |
| Side effects (legacy) | live room event, gateway notify, kind handlers, clarifier/plan ticks |
| Consumers | Still read `human_inbox` — **no journal-first UI** |
| Out of scope | `BlockExecution`, execute/merge soft authority (Slice 3), harvest `append_inbox_item`, supersede gate close, M6 deletion |

```text
Flag ON (authority):
  create: OpenExecutionGate commit → append human_inbox + notify
  resolve: CloseExecutionGate commit → resolve_inbox_item side effects

Flag OFF (rollback):
  create: append human_inbox → mirror_inbox_creation
  resolve: resolve_inbox_item → mirror_inbox_resolution
```

## Historical flags (non-runtime evidence)

| Flag | Role | Default |
| --- | --- | --- |
| `AGENT_LAB_MISSION_DUAL_WRITE` | Bridge | off unless a non-empty session allowlist selects the session |
| `AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY` | **Retired** Slice 2 authority flag (ignored) | disabled/fail-closed |

Historical implementation required both this flag and `dual_write_enabled(folder)`. The current `inbox_write_authority_enabled(folder)` is retired and always disabled/fail-closed.

## Historical rollback record (non-runtime evidence)

1. Unset / `AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY=0`.
2. Restart API.
3. Path reverts to legacy-first + `mirror_inbox_*`. Writers retained.

## Historical dogfood checklist (non-runtime evidence)

- [x] Historical API run used `DUAL_WRITE=1` + `INBOX_WRITE_AUTHORITY=1` (+ plan authority) — 2026-07-14; these authority flags are now ignored.
- [x] create question → `inbox_create_commit` · item in `human_inbox` · open_gates contains id
- [x] resolve → `inbox_resolve_commit` · pending empty · hard_mm=0
- [x] Artifact: `/tmp/agent-lab-dw-inbox-authority-20260714/reports/enable-smoke.json`

## Later slices

| Slice | Topic |
| --- | --- |
| 3 | Execute/resolve · merge/confirm soft authority (M5) |
| 4 | Hard retire / delete dual-write + legacy writers (M6) |
