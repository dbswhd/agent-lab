---
slug: wave-b-m6-retire-plan
status: plan-ready
intent: clear
pending-action: ask whether to start work or run high-accuracy review
approach: Deliver Wave B as a compatibility-safe read migration, prove UI and gate parity, then execute M6 as staged hard-retire checkpoints with rollback preserved until the final Human approval.
---

# Draft: wave-b-m6-retire-plan

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->

| id | outcome | status | evidence |
| --- | --- | --- | --- |
| WB-1 | Project a thin `mission_loop` compatibility status from Mission without cloning its action queue | active | `docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md:35-42,72-84` |
| WB-2 | Join Mission open gates to legacy `human_inbox` rows so `inbox_items` is complete and UI-safe | active | `docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md:29-33,44-54,72-77` |
| WB-3 | Move overview/inbox consumers behind a guarded read-model flag with legacy fallback and live dogfood | active | `docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md:8-13,68-90`; `web/src/utils/missionReadModel.ts:1-43` |
| M6-1 | Stop duplicate lifecycle writes only after Wave B parity and compatibility checks pass | active | `docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:38-56` |
| M6-2 | Retain payload writers, worktree/merge/Oracle implementers, and rollback bridges until explicit final approval | active | `docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:40-58` |
| M6-3 | Produce a final retire evidence packet and execute irreversible deletion only after Human approval | deferred | `docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md:79-84`; `docs/decisions/ADR-001-production-dual-write-cutover.md:53-57` |

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->

| assumption | adopted default | rationale | reversible? |
| --- | --- | --- | --- |
| Wave B rollout | Run parity first, then enable the full UI surface behind `AGENT_LAB_MISSION_UI_READ_MODEL=1`; keep flag-off fallback | Owner explicitly chose full UI immediately after parity, but mixed migrated/legacy sessions still need per-payload fallback | yes |
| `mission_loop` migration | Add only a thin compatibility projection/read adapter; do not clone the action queue | The design explicitly keeps `mission_loop` out of the journal | yes |
| M6 sequencing | Split into several retire checkpoints; remove duplicate patches before deleting payload writers or bridges | The precheck says bridges go last and several consumers still require legacy rows | yes until final deletion |
| evidence policy | Every checkpoint gets a fresh parity, UI, rollback, and failure-injection artifact; no reuse of earlier cohort evidence | Prevents stale Wave A/full-traffic evidence from authorizing deletion | yes |

## Findings (cited - path:lines)

1. Wave A is complete but intentionally non-cutover: `inbox_items` is `[]`, the UI flag is off, and Wave B is explicitly defined as mission-loop projection, inbox join, then UI preference. (`docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md:44-90`)
2. Current production UI and execute gates still read `run.json`; `HumanInboxPanel` needs full `human_inbox[]` rows, while Mission currently owns wait-state gates. (`docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:23-36`)
3. M6's safe order is already documented: journal-first read adapters, rich inbox decision payload/join, stop duplicate lifecycle patches, remove mirrors/authority flags, then dead-code/import-boundary tests. (`docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:50-58`)
4. The first M6 change must not delete `create_inbox_item`, execute/merge/Oracle implementers, or switch the UI to raw journal. (`docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:58-66`)
5. Soft authority is already enabled only when the dual-write bridge is enabled; rollback is process restart back to legacy-first. (`docs/redesign-2026-07/dual-write-retire-slice-plan-soft-2026-07-14.md:30-53`; `docs/redesign-2026-07/dual-write-retire-slice-inbox-soft-2026-07-14.md:29-42`; `docs/redesign-2026-07/dual-write-retire-slice-execution-soft-2026-07-14.md:26-34`)
6. Current implementation has the read-model route and typed client/stub, but no UI caller has replaced Composer/Inbox consumption yet. (`app/server/routers/mission_read_model.py:169-177`; `web/src/utils/missionReadModel.ts:1-43`; `docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:27-33`)

## Decisions (with rationale)

- Use a staged Wave B → M6 sequence. A single deletion PR would leave `HumanInboxPanel`, `mission_loop`, and compatibility projections without a proven replacement.
- Treat `human_inbox` rows as a compatibility/decision-surface projection until the UI can consume a complete gate-plus-row join. Mission gates remain the wait-state authority.
- Keep the dual-write and authority flags as rollback controls until the last retire checkpoint; deletion of those flags is the final irreversible change.
- After Wave B parity passes, enable `AGENT_LAB_MISSION_UI_READ_MODEL=1` for the full UI surface in the approved rollout window, with the legacy path retained as an immediate flag-off fallback.
- Execute M6 sequentially, one retire checkpoint at a time, instead of combining all writer deletion into one change.
- Project a thin Mission operational status subset into `run.json` for remaining compatibility consumers until the UI and API are fully read-model based; do not clone the full `mission_loop` action queue.

## Metis gap review (mandatory post-approval)

- The planned projector must name its concrete implementation path and field map. The repository currently has `_project_plan` in `src/agent_lab/mission/application.py:106-135`, but no `_project_mission_loop_status`; the plan must add the exact adapter, transition coverage, and a no-action-queue-clone test.
- “Full UI” means every read-model consumer, not only overview/inbox: Composer, Work status, HumanInboxPanel, SSE notification/recovery paths, autonomy/pause/circuit surfaces, and merge/Oracle/fail→repair views. Each must preserve per-payload fallback for `migrated=false`, endpoint errors, and mixed corpora (`app/server/routers/mission_read_model.py:139-166`; `web/src/components/HumanInboxPanel.tsx:605-624`; `web/src/components/ComposerEventStack.tsx:191-235`; `web/src/components/WorkToolPanel.tsx:207-219`; `web/src/hooks/useRoomSseHandler.ts:787-843`).
- The thin status projection must inventory non-UI consumers before any writer retire: `mission/tick.py:60-139`, `mission/advance.py:125-180`, `runtime/transitions.py:67-105`, `runtime/orchestration.py:69-151`, `clarity.py:411-432,489-556`, and `app/server/routers/room.py:259-289`.
- Inbox join acceptance must define ordering, duplicate IDs, missing rows, stale/terminal gates, placeholder/actionability, summary/item parity, and `mission_dual_write_verify.py:157-193` hard-mismatch behavior. The current implementation always returns empty items (`src/agent_lab/mission/read_model.py:261-301`).
- M6 checkpoints must inject crashes between Mission commit and legacy row patch, and between legacy side effects and Mission commit (`src/agent_lab/human_inbox.py:300-316`; `app/server/routers/human_inbox.py:141-158`; `app/server/routers/plan_execute.py:367-400,419-448,476-508`), then prove startup/reconcile repair, idempotent retry, and no lost prompt/options.
- Rollback is process-restart based, not a live toggle (`docs/redesign-2026-07/dual-write-operational-readiness-check-2026-07-13.md:32-44`). Every checkpoint must capture PID/commit/env/allowlist, assert a non-empty allowlist when cohorting (`src/agent_lab/mission/dual_write.py:46-55`), and preserve a tested restore point before irreversible deletion.
- The current read model hardcodes `paused=False` and derives circuit-breaker state from legacy `run.mission_loop` (`src/agent_lab/mission/read_model.py:243-258,267-278`); the plan must preserve or explicitly migrate these fields before retiring the rich projection.
- Parity cannot rely on `hard_mismatch_count=0` alone: verifier session errors are recorded separately (`scripts/mission_dual_write_verify.py:239-251`) and journal audit invalid JSON can leave duplicate count at zero (`scripts/mission_dual_write_journal_audit.py:42-57,113-119`). Require `error_count=0`, `checked == allowlist size`, `not_found=0`, audit errors=0, and invalid JSON=0.
- The final deletion gate remains unresolved until separate Human approval: soft cohort/full-traffic evidence does not itself authorize M6 hard retire (`docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:20-36,40-58`; `docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md:72-84`). The packet must include an immutable archive/checksum, exact deletion manifest, two-person approval record, and post-delete import/dead-code scan; otherwise the correct result is NO-GO.

## Scope IN

- Implement and verify `_project_mission_loop_status` or an equivalent thin compatibility adapter.
- Implement `inbox_items` as a deterministic gate-to-row join with missing-row and stale-gate handling.
- Add UI read-model canary wiring for overview/inbox with legacy fallback, then browser/manual parity checks.
- Define and execute M6 checkpoints: duplicate-writer stop, UI/default cutover, bridge retirement, and final deletion approval packet.
- Add targeted tests, failure injection, rollback smoke, and evidence artifacts for each checkpoint.

## Scope OUT (Must NOT have)

- No cloning of the full `mission_loop` action queue into Mission journal.
- No deletion of `create_inbox_item`, `human_inbox` payload writers, worktree/merge/Oracle implementers, objection BLOCK, or legacy projections before their explicit checkpoint.
- No automatic UI flag default-on, legacy writer deletion, or irreversible cleanup without Human approval.
- No schema migration or external service dependency unless separately approved.

## Open questions

All owner decisions are resolved:

- UI cutover breadth: full UI immediately after Wave B parity passes, with flag-off fallback.
- M6 deletion boundary: sequential staged retire, with each checkpoint independently verified.
- `mission_loop` compatibility shape: thin status subset projected to `run.json` until consumers migrate; no full action-queue clone.

## Approval gate
status: approved
pending-action: plan written; await execution or high-accuracy review choice
recommended-defaults: replaced by explicit owner decisions above
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->
