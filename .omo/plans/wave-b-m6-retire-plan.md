# wave-b-m6-retire-plan - Work Plan

## TL;DR (For humans)
<!-- Fill this LAST, after the detailed plan below is written, so it summarizes the REAL plan. -->
<!-- Plain English for a non-engineer: NO file paths, NO todo numbers, NO wave/agent/tool names. -->

**What you'll get:** A complete journal-first read path for mission status and human inbox content, followed by a full UI cutover with safe legacy fallback and fresh parity/soak evidence. M6 is then executed as reversible checkpoints, ending in a separately approved retire packet rather than an automatic deletion.

**Why this approach:** The Mission journal becomes lifecycle authority while `human_inbox` remains the UI payload projection, and the UI switches only after parity proves mixed migrated/legacy behavior. Writer and bridge removal stays sequential because rollback is process-restart based and several non-UI consumers still depend on compatibility fields.

**What it will NOT do:** It will not clone the full mission action queue, silently break unmigrated sessions, or delete payload writers and execution implementers early. It will not treat the existing cohort/soak GO as approval for irreversible M6 deletion.

**Effort:** XL
**Risk:** High - the UI spans mixed read sources and M6 rollback is restart-only until the final approval gate.
**Decisions to sanity-check:** Full UI enablement immediately after parity; thin `mission_loop` compatibility projection rather than an action-queue clone; sequential M6 retire with final deletion held for separate Human approval.

Your next move: start work now, or run a high-accuracy review first. Full execution detail follows below.

---

> TL;DR (machine): XL/high-risk plan delivering Wave B read-model + full UI fallback cutover, then sequential M6 retire checkpoints with immutable evidence and approval-gated deletion.

## Scope
### Must have
Wave B will make the journal-first read model complete enough for the existing UI, then enable the full UI surface immediately after parity passes. The rollout remains reversible per payload and per process: legacy data and the flag-off path stay available while mixed migrated/legacy sessions are observed.

M6 will proceed as sequential checkpoints: stop duplicate lifecycle patches first, preserve payload writers and execution implementers, prove crash/reconcile and restart rollback behavior, then retire bridges/authority flags. The final deletion manifest is prepared but is not executed without a separate explicit Human approval.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not clone the full `mission_loop` action queue into the Mission journal.
- Do not enable the UI read model blindly for unmigrated sessions; `migrated=false`, endpoint errors, stale/missing joins, and SSE gaps must fall back to the legacy payload without losing prompts or options.
- Do not delete `create_inbox_item`, `human_inbox` payload writers, worktree/merge/Oracle implementers, objection BLOCK, compatibility projections, or rollback bridges before their named checkpoint and evidence gate.
- Do not infer M6 hard-retire approval from the already-passed controlled cohort or full-traffic soak.
- Do not change schemas or add external dependencies.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: tests-after using pytest, Vitest, and Playwright; production-shaped checks use the existing live API/room dogfood harness.
- Python baseline: `.venv/bin/pytest -q tests/test_mission_read_model.py tests/test_mission_read_model_api.py tests/test_mission_dual_write.py tests/test_mission_dual_write_verify.py tests/test_human_inbox.py tests/test_room_disconnect_inbox_guard.py`.
- Web baseline: `npm --prefix web run test -- --run`; browser parity: `npm --prefix web run test:e2e -- web/e2e/plan-approval.spec.ts` plus the new read-model parity spec.
- Static consumer/import boundary: `rg -n "run\.json|mission_loop|plan_workflow|human_inbox|AGENT_LAB_MISSION_(UI_READ_MODEL|DUAL_WRITE)" src app web tests` with an allowlist checked into the evidence artifact.
- Evidence: `.omo/evidence/wave-b-m6-retire/task-<N>.json` plus the immutable production packet under `docs/redesign-2026-07/evidence/` (no secrets or PII).
- Manual QA gate: use the real browser and live API. Exercise plan approval, mid-execution question, answer/resume, pause/circuit, reconnect, fail→repair, and merge/oracle views; record console/network errors and the exact fallback branch observed.

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. Fewer than 3 (except the final) means you under-split.

- Wave 1, read contracts and compatibility: Todos 1-4 can run in parallel after the baseline inventory, but Todo 3 consumes the schemas from Todos 1-2 and Todo 4 is the deletion guard for all later waves.
- Wave 2, UI and parity: Todos 5-7 run after Wave 1. Todo 6 can run in parallel with the UI implementation once the payload contract is frozen; Todo 7 is the bounded production cutover immediately after parity passes.
- Wave 3, M6 staged retire: Todos 8-10 are strictly sequential. Each checkpoint produces a rollback artifact before the next writer/bridge is touched.
- Final verification: F1-F4 run in parallel only after every applicable todo, and the plan stops at the final Human approval gate for irreversible deletion.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1. Thin Mission operational projection | Wave A read-model baseline | 3, 4, 5, 8 | 2, 4 |
| 2. Gate-to-row inbox join | Wave A read-model baseline | 3, 5, 6 | 1, 4 |
| 3. Read-model API and parity contract | 1, 2 | 5, 6, 7 | 4 |
| 4. Consumer inventory and compatibility allowlist | current code/doc baseline | 8, 9, 10 | 1, 2, 3 |
| 5. Full UI read-model integration | 3, 4 | 6, 7 | 6 |
| 6. Parity/fallback browser and failure tests | 3 | 7, 8 | 5 |
| 7. Bounded production UI cutover and soak packet | 5, 6 | 8 | none |
| 8. Stop duplicate lifecycle patches | 7, 4 | 9 | none |
| 9. Retire bridges and authority flags | 8 plus rollback proof | 10 | none |
| 10. Final archive, approval packet, and conditional deletion | 9 plus explicit Human approval | post-delete F4 | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [x] 1. Implement thin Mission operational-status projection
  What to do / Must NOT do: Add the concrete Mission application adapter (name/path must be fixed before coding) that projects only the compatibility fields still required by `mission_loop` consumers: phase, enabled/autonomous state, pause/circuit shape, and the documented work-phase mapping. Apply it after every relevant Mission transition and keep journal events as the sole lifecycle authority. Do not copy action queues, mutable task lists, or legacy lifecycle writes into the journal.
  Parallelization: Wave 1 | Blocked by: Wave A read-model baseline | Blocks: 3, 4, 5, 8
  References (executor has NO interview context - be exhaustive): `docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md:35-42,72-84`; `src/agent_lab/mission/application.py:106-135`; `src/agent_lab/mission/tick.py:60-139`; `src/agent_lab/mission/advance.py:125-180`; `src/agent_lab/runtime/transitions.py:67-105`; `src/agent_lab/runtime/orchestration.py:69-151`; `src/agent_lab/clarity.py:411-432,489-556`.
  Acceptance criteria (agent-executable): The adapter has one named implementation and typed field map; transition tests cover plan approval/reject, execute, pause/circuit, resume, fail→repair, merge, Oracle pass/fail, and terminal states; `.venv/bin/pytest -q tests/test_mission_shadow.py tests/test_plan_workflow.py tests/test_mission_loop.py`; a static assertion proves no action-queue field is emitted.
  QA scenarios (name the exact tool + invocation): happy: pytest transition matrix and `curl` the read-model route for each fixture; failure: inject an unknown phase and assert a safe compatibility status plus an error counter, Evidence `.omo/evidence/wave-b-m6-retire/task-1.json`.
  Commit: Y | feat(mission-read-model): add thin operational status projection

- [x] 2. Implement deterministic execution-gate to inbox-row join
  What to do / Must NOT do: Replace the current empty `inbox_items` composite with a stable join of open Mission gates to `human_inbox` rows by `gate_id == item.id`, preserving the full row payload needed by HumanInboxPanel. Define duplicate-ID behavior, stable ordering, missing-row placeholders, stale/terminal gate handling, and actionability so a stale gate cannot silently create a phantom pending item. Do not make the row projection a second lifecycle authority.
  Parallelization: Wave 1 | Blocked by: Wave A read-model baseline | Blocks: 3, 5, 6
  References (executor has NO interview context - be exhaustive): `docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md:8-13,29-33,44-54,72-77`; `src/agent_lab/mission/read_model.py:205-214,261-301`; `app/server/routers/mission_read_model.py:110-166`; `web/src/components/HumanInboxPanel.tsx:605-624`; `tests/test_mission_read_model.py`; `tests/test_mission_read_model_api.py`; `tests/test_mission_dual_write_verify.py:157-193`.
  Acceptance criteria (agent-executable): For migrated, legacy, missing-row, stale-gate, duplicate-ID, terminal-orphan, and mixed fixtures, `summary.pending == len(actionable inbox_items)`; ordering is deterministic; no prompt/options disappear; `mission_dual_write_verify.py` reports zero hard mismatches for valid fixtures and classifies terminal orphans as review-only; targeted pytest files pass.
  QA scenarios (name the exact tool + invocation): happy: pytest API/composite fixtures and `curl /api/sessions/{id}/mission/read-model`; failure: delete or delay the row patch, then assert placeholder/review classification, no actionable false positive, and idempotent recomputation, Evidence `.omo/evidence/wave-b-m6-retire/task-2.json`.
  Commit: Y | feat(mission-read-model): join execution gates to inbox rows

- [x] 3. Freeze read-model API parity contract and verification harness
  What to do / Must NOT do: Expose the completed `operational_status`, overview, work phase, inbox summary, and joined items with explicit `migrated`/`source` semantics. Extend parity verification to compare normalized rows, IDs, status, options, and counts while excluding only the documented `mission_not_ready_to_execute` limitation. Keep legacy payload fields and endpoint behavior backward compatible.
  Parallelization: Wave 1 | Blocked by: Todos 1-2 | Blocks: 5-7
  References (executor has NO interview context - be exhaustive): `app/server/routers/mission_read_model.py:22-177`; `web/src/utils/missionReadModel.ts:1-43`; `web/src/api/client.ts:2661-2750`; `docs/redesign-2026-07/execution-gate-design-draft-2026-07-13.md:151-253`; `docs/redesign-2026-07/dual-write-cutover-scope-limitations-2026-07-13.md:10-25`; `tests/test_mission_read_model_api.py`; `tests/test_mission_dual_write_verify.py`.
  Acceptance criteria (agent-executable): API fixtures for migrated/legacy/mixed sessions pass; normalized parity has `mismatch=0`, `missing=0`, `unexpected_duplicate=0`, `error_count=0`, `checked == allowlist size`, and `not_found=0`; `mission_not_ready_to_execute` is counted separately; journal audit reports `invalid_json=0` and `error_count=0`; `.venv/bin/pytest -q tests/test_mission_read_model.py tests/test_mission_read_model_api.py tests/test_mission_dual_write_verify.py` passes; the typed web client builds.
  QA scenarios (name the exact tool + invocation): happy: run the verifier against the v3d/full-traffic evidence fixtures and a fresh mixed fixture; failure: corrupt one option or row ID and assert a hard mismatch with a nonzero exit, Evidence `.omo/evidence/wave-b-m6-retire/task-3.json`.
  Commit: Y | test(mission-read-model): lock parity and limitation semantics

- [x] 4. Lock the compatibility-consumer inventory and deletion allowlist
  What to do / Must NOT do: Enumerate every remaining `run.json`/`mission_loop`/`human_inbox` reader and writer, including tick/advance/transitions/orchestration/clarity/room disconnect, Composer, Work status, Inbox, SSE, autonomy, merge, and Oracle paths. Record which fields are covered by the thin projection, which remain rich compatibility data, and which are explicitly deferred. Add an import-boundary/static allowlist test used before each M6 deletion. Do not remove code in this todo.
  Parallelization: Wave 1 | Blocked by: current code/doc baseline | Blocks: 8-10
  References (executor has NO interview context - be exhaustive): `src/agent_lab/mission/tick.py:60-139`; `src/agent_lab/mission/advance.py:125-180`; `src/agent_lab/runtime/transitions.py:67-105`; `src/agent_lab/runtime/orchestration.py:69-151`; `src/agent_lab/clarity.py:411-432,489-556`; `app/server/routers/room.py:259-289`; `web/src/components/ComposerEventStack.tsx:191-235`; `web/src/components/WorkToolPanel.tsx:207-219`; `web/src/components/HumanInboxPanel.tsx:605-624`; `web/src/hooks/useRoomSseHandler.ts:787-843`; `docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:23-66`.
  Acceptance criteria (agent-executable): A checked-in allowlist names each permitted legacy read/write with owner and retirement checkpoint; `rg` output matches only allowlisted paths; the consumer inventory test fails when a new unclassified import is introduced.
  QA scenarios (name the exact tool + invocation): happy: run the inventory script and import-boundary pytest; failure: add a temporary unallowlisted reference in a fixture and assert the check fails, Evidence `.omo/evidence/wave-b-m6-retire/task-4.json`.
  Commit: Y | test(m6): lock legacy consumer and deletion allowlist

- [x] 5. Integrate the read model across the full UI surface with per-payload fallback
  What to do / Must NOT do: Wire `AGENT_LAB_MISSION_UI_READ_MODEL` into every overview/work/inbox/notification/recovery/autonomy/merge/Oracle surface identified by Todo 4. After parity passes, enable the full UI surface, not a canary, while retaining flag-off and `migrated=false`/endpoint-error fallbacks to the legacy payload. Ensure the UI does not combine raw `run.json`, `plan_workflow`, and `mission_loop` independently. Do not remove the legacy path yet.
  Parallelization: Wave 2 | Blocked by: Todos 3-4 | Blocks: 6-7
  References (executor has NO interview context - be exhaustive): `docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md:72-90`; `web/src/utils/missionReadModel.ts:1-43`; `web/src/utils/missionOverviewView.ts:1-100`; `web/src/components/ComposerEventStack.tsx:191-235`; `web/src/components/WorkToolPanel.tsx:207-219`; `web/src/components/HumanInboxPanel.tsx:605-624`; `web/src/hooks/useRoomSseHandler.ts:787-843`; `web/src/hooks/useRoomChatInteractions.ts:248-333,585`; `web/src/utils/workStatusPhase.ts:1-80`.
  Acceptance criteria (agent-executable): `npm --prefix web run build` and `npm --prefix web run lint` pass; with flag on, migrated and legacy sessions render identical pending questions/options, work phase, pause/circuit, and terminal state; `paused` and `circuit_breaker` have an explicit source/precedence test and are not lost when rich `mission_loop` projection is retired; with flag off or a 5xx, the legacy path renders without a blank/error-only surface; no component directly composes the three raw lifecycle payloads.
  QA scenarios (name the exact tool + invocation): happy: Playwright plus live browser navigation through overview→inbox→answer/resume→merge/oracle; failure: force endpoint 5xx, stale SSE, and `migrated=false`, then assert visible legacy fallback and no lost prompt/options, Evidence `.omo/evidence/wave-b-m6-retire/task-5.json`.
  Commit: Y | feat(web): consume Mission read model with safe fallback

- [x] 6. Prove parity and failure behavior at the browser and live API boundary
  What to do / Must NOT do: Add/extend browser and API parity scenarios for plan approval, mid-execution question, answer/resume, pause/circuit, reconnect, fail→repair, and merge/oracle. Treat `mission_not_ready_to_execute` as an accepted coverage counter only; all other unexplained mirror/read failures fail the gate. Do not use the previous cohort artifacts as a substitute for fresh Wave B evidence.
  Parallelization: Wave 2 | Blocked by: Todo 3; can overlap implementation with Todo 5 | Blocks: 7-8
  References (executor has NO interview context - be exhaustive): `web/e2e/plan-approval.spec.ts`; `tests/test_inbox_execute_e2e.py`; `tests/test_room_disconnect_inbox_guard.py`; `docs/redesign-2026-07/dual-write-observability-and-verification-2026-07-13.md:44-52`; `docs/redesign-2026-07/dual-write-cutover-scope-limitations-2026-07-13.md:10-25`.
  Acceptance criteria (agent-executable): `npm --prefix web run test:e2e -- web/e2e/plan-approval.spec.ts` plus the new read-model spec pass; live API checks show 100% normalized row parity for the bounded sample, zero missing/unexpected duplicates, and a separately reported `mission_not_ready_to_execute` count; browser console has no uncaught errors.
  QA scenarios (name the exact tool + invocation): happy: Playwright against a live API with a migrated and an unmigrated session; failure: inject a missing row, one mismatched option, a reconnect, and a mid-execution gate, asserting expected fallback/coverage classification, Evidence `.omo/evidence/wave-b-m6-retire/task-6.json`.
  Commit: Y | test(web): verify read-model parity and fallback flows

- [x] 7. Execute bounded production UI cutover and soak evidence
  What to do / Must NOT do: Immediately after Todo 6 parity passes, enable `AGENT_LAB_MISSION_UI_READ_MODEL=1` for the full UI surface in the approved bounded production window. Capture PID, commit, env, allowlist, request/error counters, migrated/legacy counts, coverage, and rollback instructions. Observe through the agreed soak interval and keep the legacy process/path available. Do not declare full traffic or retire a writer from this evidence alone.
  Parallelization: Wave 2 | Blocked by: Todos 5-6 | Blocks: 8
  References (executor has NO interview context - be exhaustive): `/tmp/agent-lab-dw-full-traffic-20260714/reports/soak.json`; `docs/redesign-2026-07/dual-write-full-traffic-bounded-cutover-2026-07-14.md:1-120`; `docs/redesign-2026-07/dual-write-operational-readiness-check-2026-07-13.md:5-44`; `app/server/routers/health.py:102-108`.
  Acceptance criteria (agent-executable): Bounded soak packet records zero hard mismatches, missing writes, unexpected duplicates, verifier errors, `not_found`, invalid journal JSON, uncaught browser errors, and no sustained backlog; `checked == allowlist size`; rollback is proven by capturing the v3d-style API PID/env snapshot, killing/restarting to legacy-only, and confirming journals/logs/allowlist remain intact. Full traffic GO/NO-GO is a separate evidence packet and Human decision.
  QA scenarios (name the exact tool + invocation): happy: live `curl`/room dogfood plus browser soak; failure: stop the read-model process, set flag off, restart, and verify legacy rendering and no new journal corruption, Evidence `.omo/evidence/wave-b-m6-retire/task-7.json`.
  Commit: N | ops: record bounded UI cutover and soak evidence

- [x] 8. Stop duplicate lifecycle patches while preserving side effects and repairability
  What to do / Must NOT do: At the first M6 checkpoint, disable only duplicate lifecycle patches already represented by Mission authority (plan/phase and the approved mission-loop status patch). Preserve `create_inbox_item`, human-inbox payload writers, worktree/merge/Oracle implementers, objection BLOCK, bridges, and all compatibility reads. Add failure injection around Mission commit→row patch and side-effect→Mission commit boundaries, with startup/reconcile repair and idempotent retry. Do not claim transactional rollback where the legacy side effect already landed.
  Parallelization: Wave 3 (strict sequence) | Blocked by: Todos 4 and 7 | Blocks: 9
  References (executor has NO interview context - be exhaustive): `docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:38-66`; `src/agent_lab/human_inbox.py:300-316`; `app/server/routers/human_inbox.py:141-158`; `app/server/routers/plan_execute.py:367-400,419-448,476-508`; `src/agent_lab/mission/dual_write.py:79-87,412-467`; `docs/redesign-2026-07/dual-write-retire-slice-plan-soft-2026-07-14.md:30-63`; `docs/redesign-2026-07/dual-write-retire-slice-inbox-soft-2026-07-14.md:20-49`; `docs/redesign-2026-07/dual-write-retire-slice-execution-soft-2026-07-14.md:26-41`.
  Acceptance criteria (agent-executable): targeted dual-write/inbox/execute tests pass; injected crashes leave no lost prompt/options after startup recovery and idempotent retry; an already-landed worktree/merge/Oracle side effect is reconciled exactly once; import-boundary allowlist remains unchanged except for this checkpoint; rollback restart smoke passes with captured PID/commit/env.
  QA scenarios (name the exact tool + invocation): happy: `.venv/bin/pytest -q tests/test_mission_dual_write.py tests/test_human_inbox.py tests/test_inbox_execute_e2e.py tests/test_room_disconnect_inbox_guard.py`; failure: kill at each commit boundary, run startup recovery, retry, and compare journal/run/inbox IDs, Evidence `.omo/evidence/wave-b-m6-retire/task-8.json`.
  Commit: Y | refactor(m6): stop duplicate lifecycle patches behind Mission authority

- [x] 9. Retire bridges and authority flags only after rollback proof
  What to do / Must NOT do: Remove fail-open mirror paths and authority flag registrations only after Todo 8 evidence and a fresh restore point. Assert non-empty allowlists for any remaining cohort operation, remove stale profile/env references that could silently re-enable authority, and preserve rich payload projections required by the UI. Do not delete payload writers or execution implementers in this checkpoint.
  Parallelization: Wave 3 (strict sequence) | Blocked by: Todo 8 | Blocks: 10
  References (executor has NO interview context - be exhaustive): `src/agent_lab/mission/dual_write.py:46-55,437-467`; `src/agent_lab/run/profile.py:255-305`; `docs/redesign-2026-07/dual-write-operational-readiness-check-2026-07-13.md:5-44`; `docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:44-58`.
  Acceptance criteria (agent-executable): flag/profile registry scan finds no stale re-enable path; a non-empty allowlist assertion fails closed; restart rollback from the saved tag restores legacy behavior; all targeted Python/web tests and the consumer allowlist pass; no UI prompt/options or merge/oracle path regresses.
  QA scenarios (name the exact tool + invocation): happy: run clean-process start with flags absent and exercise read/answer/execute; failure: set a stale authority env or empty allowlist and assert fail-closed/no write, then restore from tag and re-run smoke, Evidence `.omo/evidence/wave-b-m6-retire/task-9.json`.
  Commit: Y | refactor(m6): retire dual-write bridges and authority flags

- [x] 10. Produce immutable final retire packet and gate conditional deletion
  What to do / Must NOT do: Archive and checksum code/config, sessions, journals, allowlists, evidence, and the exact deletion manifest. Include full UI parity/coverage, bounded soak, rollback/restart, failure-injection/reconcile, consumer scan, and M6 checkpoint results. Obtain separate explicit Human approval (with two-person confirmation recorded by the owner) before executing any irreversible deletion; absent that approval, stop at a documented NO-GO. If approved, execute only the manifest, then run post-delete imports/dead-code scan and restore drill or record the explicit NO-ROLLBACK decision.
  Parallelization: Wave 3 (strict sequence; final gate) | Blocked by: Todo 9 plus explicit Human approval | Blocks: post-delete F4 only
  References (executor has NO interview context - be exhaustive): `docs/redesign-2026-07/journal-first-read-projection-design-2026-07-14.md:79-84`; `docs/decisions/ADR-001-production-dual-write-cutover.md:53-57`; `docs/redesign-2026-07/m6-precheck-retire-scope-2026-07-14.md:20-36,40-66`; `docs/redesign-2026-07/dual-write-full-traffic-bounded-cutover-2026-07-14.md:96-120`.
  Acceptance criteria (agent-executable): immutable archive checksum verifies; packet includes exact file/flag manifest, approver identities/timestamps, and a GO/NO-GO decision; without approval no destructive command runs; with approval, post-delete `pytest`, web build/test, `rg` import/dead-code scan, and restore/rollback check pass.
  QA scenarios (name the exact tool + invocation): happy: validate archive/checksum and run the full verification wave; failure: submit a packet without approval and assert the deletion runner exits NO-GO without mutation, Evidence `.omo/evidence/wave-b-m6-retire/task-10.json`.
  Commit: Y only after explicit approval | chore(m6): apply approved final legacy retire manifest

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit: verify every acceptance criterion, evidence path, owner decision, and no-M6-delete-before-approval guard; use `rg`/`git diff --check` and the checked-in allowlist.
- [ ] F2. Code quality review: run Python targeted tests, web lint/build/Vitest, Playwright, and import/dead-code scans; no new broad exceptions or fail-open mirrors.
- [ ] F3. Real manual QA: use the live browser/API to complete plan approval, mid-execution question, answer/resume, pause/circuit, reconnect, fail→repair, and merge/oracle on migrated and legacy sessions; record console/network output.
- [ ] F4. Scope fidelity: confirm no full action-queue clone, no unapproved writer/implementer deletion, no schema/dependency drift, and final M6 status is NO-GO until the separate Human approval is present.

## Commit strategy

Keep commits atomic and reversible: read-model projection, inbox join, parity contract, consumer allowlist, UI integration, then one M6 checkpoint per commit. Operational evidence-only steps do not create code commits. Any deletion commit must contain only the approved manifest and must be impossible to run when the approval artifact is absent. Never combine UI cutover with writer deletion.

## Success criteria

- Wave B returns non-empty, deterministic `inbox_items` for valid open gates and preserves full prompt/options across migrated, legacy, mixed, stale, and failure fixtures.
- The thin Mission operational projection satisfies all enumerated non-UI consumers without cloning the action queue or creating a second lifecycle authority.
- Every UI surface uses the read-model contract when enabled, falls back safely per payload when disabled/unmigrated/error, and passes browser parity for the approved scenarios.
- Bounded production UI cutover and soak are evidenced with zero unexplained mismatch, missing write, unexpected duplicate, or uncaught browser error; `mission_not_ready_to_execute` is reported separately as the accepted FSM limitation.
- M6 duplicate lifecycle patches are removed only after failure-injection/reconcile and restart rollback evidence; payload writers, worktree/merge/Oracle implementers, and bridges remain until their checkpoints.
- Final hard retire is either (a) explicitly approved, archived, checksummed, executed only from the manifest, and post-delete verified, or (b) documented NO-GO with no destructive mutation.
