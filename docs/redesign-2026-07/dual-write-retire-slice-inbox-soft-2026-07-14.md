# Dual-write retire Slice 2 — Inbox execution-gate soft authority

> **작성:** 2026-07-14  
> **상태:** **Human enable GO** · supersede gate close + harvest OpenExecutionGate completed with Slice 3 batch (2026-07-14).  
> **선행:** Slice 1 plan soft authority enable GO · Full traffic soak PASS.  
> **관련:** [Slice 1 plan](./dual-write-retire-slice-plan-soft-2026-07-14.md) · [ADR-001](../decisions/ADR-001-production-dual-write-cutover.md) · [execution-gate design](./execution-gate-design-draft-2026-07-13.md)

## Slice definition

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

## Flags

| Flag | Role | Default |
| --- | --- | --- |
| `AGENT_LAB_MISSION_DUAL_WRITE` | Bridge | off (process opt-in) |
| `AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY` | Slice 2 soft retire | **on** in balanced/thorough/autonomous |

`inbox_write_authority_enabled(folder)` requires both this flag and `dual_write_enabled(folder)`.

## Rollback

1. Unset / `AGENT_LAB_MISSION_INBOX_WRITE_AUTHORITY=0`.
2. Restart API.
3. Path reverts to legacy-first + `mirror_inbox_*`. Writers retained.

## Dogfood checklist

- [x] API: `DUAL_WRITE=1` + `INBOX_WRITE_AUTHORITY=1` (+ plan authority) — 2026-07-14
- [x] create question → `inbox_create_commit` · item in `human_inbox` · open_gates contains id
- [x] resolve → `inbox_resolve_commit` · pending empty · hard_mm=0
- [x] Artifact: `/tmp/agent-lab-dw-inbox-authority-20260714/reports/enable-smoke.json`

## Later slices

| Slice | Topic |
| --- | --- |
| 3 | Execute/resolve · merge/confirm soft authority (M5) |
| 4 | Hard retire / delete dual-write + legacy writers (M6) |
