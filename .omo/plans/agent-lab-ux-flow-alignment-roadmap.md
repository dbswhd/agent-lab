# agent-lab-ux-flow-alignment-roadmap - Work Plan

## Scope
### Must have
- Current product flow is explicit and testable: topic intake, risk/intent routing, one Decision Queue item, plan approval/revision, worktree dry-run, diff/merge approval, Oracle, repair/re-discuss, and PASS-only completion.
- Composer Decision Queue and topic-only Composer remain the UX SSOT; Work tab and Plan toggle are not reintroduced.
- Documentation, browser acceptance, routing rollout, Mission authority rollout, and operational gates are aligned to that contract.
### Must NOT have (guardrails, anti-slop, scope boundaries)
- No gate bypass, automatic plan/execute/merge/repair approval, or PASS without Oracle evidence.
- No full-traffic Mission cutover, legacy writer hard delete, or data deletion.
- No adaptive/authority default flip before the evidence gates below pass and a Human GO is recorded.
- No unrelated trading/quant surface expansion or broad UI rewrite.
- Large component splitting and bundle optimization are a separate follow-up after lifecycle acceptance; they do not block this plan.

## Verification strategy
> Automated verification is agent-executed; product authority decisions remain explicit Human gates and must be recorded, never simulated by a test.
- Test decision: TDD for routing, lifecycle, authority, and browser behavior; tests-after for documentation-only corrections. Use pytest, Vitest, Playwright, build, and existing smoke/dogfood scripts.
- Evidence: `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-<N>.*` plus command logs and screenshots/traces for browser failures. Every task records both happy and failure-path evidence.
- Provenance: every evidence record includes commit SHA, UTC timestamp, command, exit code, environment/profile and flag snapshot, cohort/session IDs, and raw artifact path.
- Baseline commands: `make test-fast`, `cd web && npm run test -- --run`, `cd web && npm run build`, `python scripts/smoke_room.py`.
- Browser gate: `cd web && npx playwright test e2e/ui-simplification.spec.ts e2e/wave-b-journey.spec.ts`; Wave B must be 4/4 after navigation is made independent of Dogfood classification.
- Targeted backend gates: `pytest -q tests/test_turn_contract.py tests/test_turn_contract_runtime.py tests/test_mcp_first_inbox.py tests/test_plan_workflow.py tests/test_plan_execute_agent_repair.py tests/test_room_disconnect_inbox_guard.py tests/test_mission_topology_wire.py tests/test_n9_verify_api.py`.
- Operational evidence: `make f7-dogfood-report`, `make dogfood-track`, and one recorded success plus one FAIL→repair/re-discuss dogfood session. Reports must distinguish mock, browser, and live evidence.
- Human-gate evidence: each gate records `pre_state → Human action → API command → post_state → negative assertion` for plan approve/revise, dry-run/execute, diff/merge/abort, Oracle FAIL repair, and retry-cap re-discuss. Tests assert that no auto-approved action closes these gates.

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. Fewer than 3 (except the final) means you under-split.

- Wave 1 (truth baseline and behavior proof): Todo 1 establishes terminology/status; then Todos 2-4 can proceed in parallel against that frozen contract.
- Wave 2 (controlled rollout): Todo 5 establishes shadow routing evidence; then Todos 6-7 can proceed in parallel while remaining cohort/shadow gated.
- Wave 3 (readiness): Todo 7 completes the evidence package after the controlled rollout; component/bundle hardening is explicitly deferred to a follow-up plan.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 2, 3, 4 | none |
| 2 | 1 (terminology/SSOT only) | 5 | 3, 4 |
| 3 | 1 (truth status only) | 5, 6 | 2, 4 |
| 4 | 1 | 5, 6 | 2, 3 |
| 5 | 2, 3, 4 | 6, 7 | none |
| 6 | 5 | final verification | 7 |
| 7 | 5 | final verification | 6 |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [ ] 1. Rebaseline the UX and status documentation around the current Composer Decision Queue contract
  What to do / Must NOT do: Replace stale Work tab, Workbench, and Plan toggle instructions with topic-only Composer, Decision Queue, current workspace tabs, and the confirmed lifecycle. Include `.agent-lab/PROJECT.md` in the SSOT pass, and explain that the internal Composer `work` lane is not the removed Work navigation tab. Correct current status to “not browser-accepted” while Wave B is red; only Todo 7 may later restore a shipped/complete claim. Preserve historical references as clearly labelled archive material. Do not alter product code or mark a red browser gate as shipped.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 2, 3, 4
  References (executor has NO interview context - be exhaustive): `.agent-lab/PROJECT.md:1-13`, `docs/USER-GUIDE.md:200-231,397-412`, `docs/05-room-agent-roles.md:1-29`, `docs/FLOW.md:48-68,199-215`, `docs/NOW.md:30-38`, `docs/NOW.md:79`, `docs/redesign-2026-07/11-ui-ux-surface-map.md:1-24,68-85,134`, `docs/EXTERNAL-REFS-TRACEABILITY.md`, `web/src/utils/roomComposerPrefs.ts:3-7`, `web/src/utils/workspaceTabs.ts:13-34`
  Acceptance criteria (agent-executable): `rg` finds no current-state claim that Work is a live tab or that Composer exposes a Plan toggle; docs explicitly state Decision Queue precedence and current Wave B status; markdown/link checks pass; `git diff --check` passes.
  QA scenarios (name the exact tool + invocation): happy: inspect all canonical links and current-state tables; failure: intentionally search for `Work tab`, `Plan toggle`, and `Wave B 4/4` in current sections and confirm only archive/history references remain. Evidence `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-1.md`.
  Commit: Y | `docs(ux): rebaseline Decision Queue lifecycle contract`

- [ ] 2. Make browser session navigation independent of Dogfood classification and fixture naming
  What to do / Must NOT do: Add stable session selectors or direct session-id navigation to the browser fixture, and make the Wave B setup select the intended session regardless of Sessions/Dogfood rail classification. Keep the production classification behavior unchanged unless a separate regression proves it wrong. Do not hide timeouts by increasing default test timeout.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 5
  References (executor has NO interview context - be exhaustive): `web/e2e/wave-b-journey.spec.ts:415-425,427-523`, `web/src/utils/dogfoodSessions.ts:3-32`, session rail/list component and route used by `openSession`, `web/e2e/ui-simplification.spec.ts`
  Acceptance criteria (agent-executable): `cd web && npx playwright test e2e/wave-b-journey.spec.ts`; all four tests enter the intended session and no test relies on a visible tab label that can change with classification. A deliberately Dogfood-classified fixture still opens by stable identity.
  QA scenarios (name the exact tool + invocation): happy: run Wave B with existing fixture names; failure: classify the same fixture as Dogfood and rerun, confirming the same session opens. Evidence `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-2.md` plus Playwright trace on failure.
  Commit: Y | `test(web): stabilize session navigation for Wave B journeys`

- [ ] 3. Add a browser golden journey with evidence assertions for every human gate
  What to do / Must NOT do: Add one connected Playwright journey from topic input through Room routing, single active Decision Queue CTA, plan approve/revise, worktree dry-run, diff/merge approval, Oracle PASS, and FAIL→repair/re-discuss→PASS; retain isolated gate tests for fast diagnosis. Define a gate ledger for each `pre_state → Human action → API → post_state → negative assertion`. Assert command POSTs and read-model/SSE convergence, including plan hash/revision, execution/diff, merge SHA/checks, Oracle evidence, repair attempt, and final audit. Active rendering must contain exactly one `decision_id`; multiple Inbox items may be queued but only the canonical backend ordering (priority, then creation/order key, then stable ID) may promote the next item. Keep Human gates explicit; mocks must not imply that production auto-approves.
  Parallelization: Wave 1 | Blocked by: 1 (truth status) | Blocks: 5, 6
  References (executor has NO interview context - be exhaustive): `web/src/components/ComposerEventStack.tsx`, `web/src/utils/composerStackLane.ts:23-101`, `web/src/components/PlanApprovalPanel.tsx`, `web/src/components/WorkToolPanel.tsx`, `web/e2e/wave-b-journey.spec.ts:427-523`, `docs/FLOW.md:149-215`, `docs/redesign-2026-07/11-ui-ux-surface-map.md:26-40`
  Acceptance criteria (agent-executable): `web/e2e/agent-lifecycle-journey.spec.ts` covers one connected complete happy path and a failure-repair path; each stage asserts one primary CTA, one active `decision_id`, matching request, expected version transition, next phase, and durable evidence. Final PASS requires a non-empty `commit_sha`, green merge checks, `oracle.verdict == pass`, no pending decision, no repair failure counted as success, `MISSION_DONE`/`SUCCEEDED`, merge provenance, and run audit. Cohort runs assert `approved_by != auto` and zero trust-budget auto-merge. `cd web && npx playwright test e2e/agent-lifecycle-journey.spec.ts` passes.
  QA scenarios (name the exact tool + invocation): happy: complete all gates to PASS; failure: make Oracle return FAIL, verify REPAIRING/re-discuss and bounded retry, then verify PASS; stale: answer an old Decision Queue item and expect 409 without state corruption. Evidence `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3.md`.
  Commit: Y | `test(web): cover Decision Queue to Oracle golden journey`

- [ ] 4. Verify and correct lifecycle/read-model behavior exposed by the Decision Queue
  What to do / Must NOT do: Compare ComposerEventStack lane precedence and read-model/runtime/legacy fallback against the golden journey. Fix only concrete mismatches such as hidden CTAs, stale phase projection, or queue ordering that prevents the confirmed sequence. Preserve one active blocking decision and all existing Human gates; do not restore Work tab semantics.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 5, 6
  References (executor has NO interview context - be exhaustive): `web/src/components/ComposerEventStack.tsx`, `web/src/utils/composerStackLane.ts:23-101`, `web/src/utils/workspaceTabs.ts:23-78`, `web/src/components/PlanApprovalPanel.tsx`, `web/src/components/WorkToolPanel.tsx`, `src/agent_lab/runtime/work_phase.py`, `docs/ROOM-TRANSCRIPT-CONTRACT.md`, `docs/MCP-FIRST-INBOX.md`
  Acceptance criteria (agent-executable): unit tests prove lane order `plan_approval → execute_queue → consensus → inbox → clarify → work`; component/browser tests prove read-model precedence and legacy fallback do not expose a stale or duplicate CTA; `cd web && npm run test -- --run` passes.
  QA scenarios (name the exact tool + invocation): happy: pending plan then execute resolves to the next single CTA; failure: pending inbox plus plan approval keeps plan as active and exposes inbox only as queued hint; reconnect: replayed durable event does not duplicate the decision. Evidence `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-4.md`.
  Commit: Y | `fix(web): align Decision Queue projection with lifecycle contract`

- [ ] 5. Instrument TurnContract shadow evidence and define the routing promotion gate
  What to do / Must NOT do: Preserve `shadow` as the default and supervisor implicit preset. Record candidate/applied contract, safety-floor result, roster/round/consensus, latency/cost, route regret, and shadow/applied parity per session. Add tests for history minimum, deterministic exploration, and high-risk safety floors. Proposed promotion gate is at least 10 eligible sessions and a 7-day green window per stage, safety-floor violations 0, critical-task under-routing 0, shadow/applied parity ≥99.5%, and p95 latency regression ≤10%; a Human may revise these thresholds before GO. Do not flip `AGENT_LAB_TURN_CONTRACT_MODE` globally.
  Parallelization: Wave 2 | Blocked by: 2, 3, 4 | Blocks: 6, 7
  References (executor has NO interview context - be exhaustive): `src/agent_lab/room/turn_contract.py:142-158`, `src/agent_lab/room/preset.py`, `docs/TURN-POLICY.md`, `docs/FLOW.md:62-68`, `tests/test_turn_contract.py`, `tests/test_turn_contract_runtime.py`, `tests/test_fast_inbox_skip.py`
  Acceptance criteria (agent-executable): targeted pytest passes; shadow ledger contains candidate/applied/safety-floor/latency fields; safety-floor violations are zero in the test corpus; no default config or implicit multi-agent supervisor behavior changes; report includes a documented threshold and Human GO checkpoint for `roles` then `adaptive`.
  QA scenarios (name the exact tool + invocation): happy: low-risk topic selects lightweight candidate while high-risk retains critical floor; failure: unsafe candidate is rejected and recorded; insufficient history remains deterministic. Evidence `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-5.md`.
  Commit: Y | `feat(room): add shadow routing evidence and promotion gates`

- [ ] 6. Expand Mission authority only through plan-first bounded cohorts
  What to do / Must NOT do: Exercise authority in an explicit matrix because plan/execution use `AGENT_LAB_MISSION_DUAL_WRITE` plus `AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS` and per-surface flags, while Inbox uses `AGENT_LAB_MISSION_AUTHORITY` plus `AGENT_LAB_MISSION_AUTHORITY_SESSIONS`. Decide and record whether one cohort is in both allowlists or surfaces use separate cohorts. Roll out plan approve/reject first, then MCP-first Inbox open/resolve, then execution/merge/Oracle commit. Verify parity, idempotency, stale/duplicate 409, process restart, and legacy-first rollback. Use a disposable git repository and real route calls for execution authority before expanding the cohort. Keep non-cohort writers and empty-allowlist behavior unchanged. Do not enable full traffic or hard-delete legacy writers.
  Parallelization: Wave 2 | Blocked by: 5 and all browser gates | Blocks: final verification
  References (executor has NO interview context - be exhaustive): `src/agent_lab/mission/dual_write.py:51-109,218-299,329-452`, `src/agent_lab/plan/execute_merge.py`, `docs/NOW.md:31-38`, `docs/MCP-FIRST-INBOX.md`, `tests/test_mcp_first_inbox.py`, `tests/test_plan_workflow.py`, `tests/test_plan_execute_agent_repair.py`, `tests/test_room_disconnect_inbox_guard.py`, `tests/test_mission_topology_wire.py`, `tests/test_n9_verify_api.py`
  Acceptance criteria (agent-executable): an authority matrix covers plan-only, Inbox-only, both, and neither cohort combinations; cohort tests pass with the correct flags; journal/run projection divergence is zero; duplicate/stale answer returns 409; kill/restart recovers without duplicate side effects; disposable-repo execution/merge/Oracle route calls prove real side effects are gated; rollback by removing allowlist returns to legacy-first; a Human GO record is required before each authority expansion.
  QA scenarios (name the exact tool + invocation): happy: plan approval→Inbox resolve→execute/merge/Oracle mirrors and commits in order; failure: mirror mismatch circuit-breaks the cohort and preserves append-only journal; rollback: unset authority flags and verify legacy path. Evidence `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-6.md`.
  Commit: Y | `feat(mission): gate authority rollout by bounded cohort evidence`

- [ ] 7. Run dogfood readiness and repair-loop measurement before any default change
  What to do / Must NOT do: Re-run browser, smoke, dogfood, and feedback reports using one success and one FAIL→repair/re-discuss session. Separate mock, browser, and live evidence; measure Oracle coverage, false-success, repair attempts, retry plateau, gate latency, and cohort/non-cohort parity. Record sample size, data window, owner, threshold, commit SHA, flags, cohort IDs, and raw artifacts. Only after these evidence gates are green may the docs restore shipped/complete language. Do not declare readiness from a single mock or stale report.
  Parallelization: Wave 2 | Blocked by: 5 | Blocks: final verification
  References (executor has NO interview context - be exhaustive): `docs/NOW.md:54-87`, `scripts/smoke_room.py`, `make f7-dogfood-report`, `make dogfood-track`, feedback report scripts and `docs/EMERGENCE-BENCH.md`, `docs/EXTERNAL-REFS-TRACEABILITY.md`
  Acceptance criteria (agent-executable): `make test-fast`, web tests/build, smoke, Wave B 4/4, and dogfood reports complete; success and FAIL→repair sessions have preserved artifacts and Oracle verdict/evidence; F7/N4-D3/HS-M5 status is explicitly PASS, OPEN, or deferred with owner and next gate; shipped/complete documentation claims are updated only after the new green browser evidence; no default flip occurs solely from this report.
  QA scenarios (name the exact tool + invocation): happy: PASS path closes only after Oracle; failure: Oracle FAIL returns to repair/re-discuss and stops after retry cap for Human decision; operational: restart during a gate recovers. Evidence `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7.md`.
  Commit: Y | `chore(ops): record dogfood readiness and repair evidence`

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit: confirm every Must have/guardrail and every Human gate is represented in code, tests, and evidence; no Work tab restoration or authority bypass.
- [ ] F2. Code quality review: inspect changed files, test coverage, fallback/rollback behavior, and reject unrelated churn; defer module/bundle hardening to a follow-up plan.
- [ ] F3. Real manual QA: execute the browser golden journey and one FAIL→repair/re-discuss journey against the running app, recording screenshots/traces and checking single-CTA behavior.
- [ ] F4. Scope fidelity: verify docs, traceability, NOW status, and reports describe the same current truth; require explicit Human GO before routing/authority default changes.

## Commit strategy
- One focused commit per todo, with documentation, behavior, and tests kept together for that todo.
- Do not commit generated sessions, reports, screenshots, traces, or user-owned scratch files; attach them under `.omo/evidence/` only when they are part of the verification artifact.
- Keep rollout flag changes separate from implementation commits so rollback is an env/allowlist change, not a code revert.

## Success criteria
- A user can follow one connected, unambiguous path from topic input to PASS-only completion, with one current Decision Queue action and one active `decision_id` at each Human gate.
- Plan approval, worktree dry-run, diff/merge approval, Oracle verdict, repair/re-discuss, and final audit are all visible and independently evidenced.
- Browser acceptance is green (Wave B 4/4 plus the full golden journey), and documentation no longer claims removed surfaces or unverified completion.
- TurnContract remains safe under shadow and has measured promotion gates; Mission authority remains cohort-bounded until explicit Human GO.
- All baseline and targeted tests pass, with rollback and restart evidence recorded.

## TL;DR (For humans)
**What you'll get:** A single, truthful user journey from entering a topic through Room discussion, Decision Queue approvals, isolated execution, diff/merge review, Oracle verification, repair, and PASS-only completion. The browser tests and operating documents will prove the same journey users see.

**Why this approach:** We first make the current Composer Decision Queue contract and browser evidence truthful, then use that stable evidence to judge routing and Mission authority rollouts safely in bounded steps.

**What it will NOT do:** It will not restore the removed Work tab, bypass Human approvals, or enable global authority/default changes automatically. It will not delete legacy data or expand unrelated product surfaces.

**Effort:** XL
**Risk:** High - the work crosses UI, browser acceptance, routing, Mission authority, and operational rollout gates.
**Decisions to sanity-check:** Keep Decision Queue as the UX SSOT; keep TurnContract shadow and Mission authority cohort-bounded until explicit evidence-based Human GO.

Your next move: execute the plan in order, stopping at each Human GO gate; implementation has not started as part of plan writing.

---

> TL;DR (machine): XL/high; align UX/docs, restore end-to-end browser evidence, then gate routing and Mission authority rollout with rollback and PASS-only completion.
