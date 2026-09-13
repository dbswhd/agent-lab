# Task 4 — Decision Queue projection verification

Recorded at `17ef052ecd264d9c99ca9b60b9fe5d4ccca6ec5d`.

## Verification

| Scenario | Invocation | Exit | Binary observable | Provenance |
| --- | --- | ---: | --- | --- |
| Targeted web unit coverage | `cd web && npx vitest run src/components/ComposerEventStack.test.tsx src/components/HumanInboxPanel.test.ts src/utils/composerStackLane.test.ts src/utils/missionReadModel.test.ts` | 0 | 4 files / 29 tests passed | Shared worktree at verified HEAD; no raw artifact persisted |
| Full web unit suite | `cd web && npm run test -- --run` | 0 | 43 files / 185 tests passed | Shared worktree at verified HEAD; no raw artifact persisted |
| Production build | `cd web && npm run build` | 0 | TypeScript + Vite build passed | Shared worktree at verified HEAD; no raw artifact persisted |
| Isolated stale lifecycle | `cd web && npx playwright test e2e/agent-lifecycle-journey.spec.ts --grep 'stale expected_version' --reporter=line` | 0 | 1 passed | Verifier-reported from temporary archive at `49030edf`; applicable to `17ef052e` because the sole intervening commit changed only `web/e2e/wave-b-journey.spec.ts`; archive not persisted |
| Full lifecycle | `cd web && npx playwright test e2e/agent-lifecycle-journey.spec.ts --reporter=line` | 0 | 5 passed | Verifier-reported from temporary archive at `49030edf`; applicable to `17ef052e` because the sole intervening commit changed only `web/e2e/wave-b-journey.spec.ts`; archive not persisted |
| Whitespace integrity | `git diff --check` | 0 | no whitespace errors | Shared worktree at verified HEAD; no raw artifact persisted |

The targeted/unit/build/diff commands ran in the shared worktree. Only Playwright ran in a temporary archive at `49030edf`; those results apply to verified HEAD `17ef052e` because the sole intervening commit changed only `web/e2e/wave-b-journey.spec.ts`, outside lifecycle/config/Task 4 paths. No fresh browser raw path is claimed, and no stale reviewer report is used as proof of the fresh 1/1 and 5/5 results.

## Manual browser observable

Older Task 3 context shows one `data-active-decision-id` stack and exactly one approval/submit CTA while a second pending question is represented as queued. Reused artifacts: [raw lifecycle output](task-3/raw/exact-final-command.log) and [browser screenshot](task-3/browser/single-active-decision-queued.png). These are context only, not fresh Task 4 evidence. Fresh Task 4 browser outcomes are verifier-reported from the temporary archive at `49030edf`; they apply to `17ef052e` because only `web/e2e/wave-b-journey.spec.ts` changed between those commits, and no fresh raw artifact is persisted.

## UltraQA matrix

| Scenario | Result |
| --- | --- |
| stale state | PASS — rendered precedence assertions cover read-model → runtime → legacy. |
| reconnect/replay duplication | PASS — fresh verifier lifecycle checks report one active decision/CTA; older Task 3 raw output is context only. |
| dirty worktree | PASS — unrelated dirt preserved; repair touched only Task 4 evidence. |
| misleading success output | PASS — DOM assertions inspect lane, decision id, queue hint, CTA count, and omitted second question. |
| malformed payload | PASS — read-model malformed-input cases run in targeted/full unit gates. |
| mid-operation interrupt/cancel | N/A — no new cancellable operation in this synchronous projection. |

The standalone projection-helper test is weak/redundant evidence by itself; it remains supplementary. The meaningful regression proof is the rendered `HumanInboxPanel`/`ComposerEventStack` coverage plus the browser observable.

## Cleanup and scope

No QA process was started by this repair, no product/test/plan/docs files were changed, and all unrelated modified/untracked worktree files were preserved. Existing Task 3 artifacts were referenced read-only.
