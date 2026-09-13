# Todo 4 Final Gate Review

recommendation: **APPROVE**

## Original intent

Keep the Composer Decision Queue as the single user-facing Human-action surface while correcting only concrete lifecycle/read-model mismatches. Preserve the existing lane order, prefer read-model over runtime over legacy state, expose one active `decision_id` and one active Inbox CTA, queue later Inbox items, reject stale/replayed actions without duplicating the CTA, and do not restore removed Work navigation semantics.

## Desired outcome

A user sees exactly one current Decision Queue action at a time. Newer lifecycle projections cannot be overwritten by stale runtime or legacy phase data; additional pending Inbox items appear only as a queued hint; replay/reconnect does not duplicate the active action.

## User outcome review

The shipped component behavior satisfies the intended Todo 4 outcome:

- `COMPOSER_STACK_LANE_ORDER` remains `plan_approval → execute_queue → consensus → inbox → clarify → work`.
- `ComposerEventStack` resolves phase as read-model → runtime → legacy and exposes the canonical first durable gate as `data-active-decision-id`.
- A pending plan approval remains the sole active CTA while Inbox work is represented as queued.
- `HumanInboxPanel` renders only the first canonical pending item, exactly one Submit CTA, and a queued-count hint; the second question is absent from rendered markup.
- The internal `work` lane remains a Composer lane. No Work navigation surface was added by the reviewed commits.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| T4-AC1 lane order unchanged | PASS | `web/src/utils/composerStackLane.ts`; `web/src/utils/composerStackLane.test.ts`; independent targeted run: 29/29 tests passed |
| T4-AC2 read-model → runtime → legacy precedence | PASS | `web/src/components/ComposerEventStack.tsx`; rendered SSR cases in `web/src/components/ComposerEventStack.test.tsx` use differing phases and passed |
| T4-AC3 one active decision/CTA with queued hint | PASS | `web/src/components/HumanInboxPanel.tsx`; rendered SSR assertion in `web/src/components/HumanInboxPanel.test.ts`; raw browser evidence and screenshot listed below |
| T4-AC4 stale/reconnect does not duplicate CTA | PASS | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/exact-final-command.log`; `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/flaky-repeat-3x.log`; lifecycle spec assertions require exactly one `[data-active-decision-id]` and one active CTA |
| T4-AC5 full web unit suite | PASS | Independently reproduced: `npm run test -- --run` → 43 files, 185 tests passed |
| T4-AC6 no Work navigation restoration | PASS | Reviewed diff `b51afebf^..f64fe74e`; changes are confined to Composer/Inbox projection and tests |

## Adversarial review

- stale_state: PASS. SSR precedence tests distinguish all three sources; browser raw artifact records the stale `expected_version` 409 scenario passing.
- reconnect_duplication: PASS. Browser raw artifact records reload/reconnect resuming the same operation without duplicate decision; rendered assertions require a single active decision node.
- dirty_worktree: PASS for behavior evidence. The lifecycle suite includes a dirty-worktree scenario and the raw run passed.
- misleading_success_output: PASS. Claims are backed by rendered HTML assertions, exact CTA counts, decision-id selectors, browser logs, and a screenshot rather than helper-return assertions alone.
- flaky_tests: PASS. Raw artifact records 15/15 across three repeated lifecycle runs; independent unit runs also passed.
- malformed_payload: PASS. The lifecycle raw run includes malformed decision payload rejection; `missionReadModel` parser tests were independently included in the 29/29 targeted run.
- runtime: N/A as a new production runtime. Todo 4 changes synchronous UI projection only; existing browser lifecycle runtime was exercised by supplied raw artifacts.

## Direct remove-ai-slops / programming pass

- The strengthened `HumanInboxPanel` test is not merely implementation-mirroring: it renders the actual component and checks visible first-question content, absence of the queued question, the queued hint, and exactly one Submit CTA.
- The pure projection helper test alone would have been insufficient, but the later rendered-component regression closes that gap.
- Precedence fixtures differ from their fallbacks, so they fail if source ordering regresses.
- No deletion-only test, requested-removal string pin, tautological expected value, speculative production parser/normalizer, or new runtime abstraction was introduced in Todo 4.
- NOTE: `HumanInboxPanel.tsx` and the Task 3 lifecycle spec exceed the skill's preferred module-size ceiling. That maintenance concern is not a failure of a stated Todo 4 acceptance criterion. The available Task 3 code-review report explicitly applies both skill perspectives and flags the oversized/mock-heavy Task 3 E2E separately.

## Checked artifacts

- `.omo/plans/agent-lab-ux-flow-alignment-roadmap.md`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-4.json`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/exact-final-command.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/flaky-repeat-3x.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/web-unit.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/web-build.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/single-active-decision-queued.png`
- `.omo/evidence/task-3-code-review.md`
- `web/src/components/ComposerEventStack.tsx`
- `web/src/components/ComposerEventStack.test.tsx`
- `web/src/components/HumanInboxPanel.tsx`
- `web/src/components/HumanInboxPanel.test.ts`
- `web/src/utils/composerStackLane.ts`
- `web/src/utils/composerStackLane.test.ts`
- `web/src/utils/missionReadModel.test.ts`
- `web/e2e/agent-lifecycle-journey.spec.ts`

## Independent commands

- `npx vitest run src/components/ComposerEventStack.test.tsx src/components/HumanInboxPanel.test.ts src/utils/composerStackLane.test.ts src/utils/missionReadModel.test.ts` → PASS, 4 files / 29 tests.
- `npm run test -- --run` → PASS, 43 files / 185 tests.
- `npm run build` → PASS, TypeScript and Vite build completed; only the pre-existing chunk-size warning.
- `git diff --check` → PASS.

## Evidence gaps and notes

- No standalone `task-4.md`, raw Task 4 command directory, or Task 4-specific code-review report exists. `task-4.json`, the Task 3 raw lifecycle artifacts reused by Task 4, the direct source/test inspection, and independently reproduced unit/build gates are sufficient for the stated criteria.
- The current worktree acquired concurrent uncommitted changes to `web/playwright.config.ts` (`VITE_SKIP_API=1`, alternate port handling) and an untracked `.venv` link during review. Consequently, the exact Playwright stale scenario could not be cleanly re-run against the committed server-start configuration in the final dirty snapshot: the modified configuration skipped API startup and produced proxy `ECONNREFUSED`. This is an exact current-environment gap, not source evidence of a Todo 4 regression. The committed/raw artifact records the exact lifecycle suite passing, including 3 repeated runs.

## Blockers

None.
