# Task 3 visual oracle A r2 — gate review

## recommendation

APPROVE

## blockers

None.

## originalIntent

Task 3 must add a browser golden journey from topic intake through one active
Decision Queue action, explicit Human plan/execution/merge gates, Oracle PASS,
and Oracle FAIL → repair/re-discuss → PASS. The rendered browser state and the
read model must agree, and completion must never be shown before Oracle PASS.

## desiredOutcome

- A single active `decision_id` and CTA is visible at each blocking Human gate;
  additional items may remain queued.
- A successful journey ends at a truthful Oracle PASS surface with no active
  decision, stale Execute notice, or Execute CTA.
- An Oracle FAIL remains visibly in repair and cannot be mistaken for success.
- The repaired journey closes only after bounded retry reaches Oracle PASS.

## userOutcomeReview

The current artifacts satisfy the requested user-visible outcome.

- `single-active-decision-queued.png` shows one expanded question with one
  Submit CTA and text indicating one further queued item.
- `happy-final-pass.png` and `repair-final-pass.png` visibly show mission
  complete, `Verified loop pass`, Oracle `통과`, and `검증 완료`. Neither capture
  contains `Execute 승인 필요`, an Execute CTA, or an active Decision Queue card.
- `repair-oracle-fail.png` visibly shows mission `수정 중`, `Verified loop fail`,
  an active change-review decision, and `Oracle 재검증`; it does not present a
  completion state.

The two final PNGs are byte-identical. That is consistent with both scenarios
converging to the same final state and is supported by separate scenario
execution in the repeat log; it is not itself a failure.

## criterion review

| criterion | result | evidence |
|---|---|---|
| T3-C1 connected Human-gated golden journey | PASS | `.omo/plans/agent-lab-ux-flow-alignment-roadmap.md:64-69`; `web/e2e/agent-lifecycle-journey.spec.ts:1129` |
| T3-C2 exactly one active decision/CTA, queued items allowed | PASS | `browser/single-active-decision-queued.png`; `assertSingleActiveDecision` |
| T3-C3 PASS only with merge/check/Oracle evidence and no pending decision | PASS | `expectFinalAudit`, `assertFinalBrowserSurface`, `browser/happy-final-pass.png` |
| T3-C4 FAIL remains REPAIRING/re-discuss and bounded retry reaches PASS | PASS | repair scenario assertions; `browser/repair-oracle-fail.png`; `browser/repair-final-pass.png` |
| T3-C5 no Human-gate auto-approval | PASS | `expectFinalAudit` checks `approved_by`, auto-merge requests, trust budget, and execution audit |
| T3-C6 stale answer returns 409 without state corruption | PASS | stale scenario and `raw/exact-final-command.log` |

## direct remove-ai-slops / programming pass

The current diff changes only the Playwright fixture/test file.

- Removing `actions` and `plan-actions` in the `succeeded` fixture is necessary:
  the final UI consumes those fixture endpoints, and retaining the recommended
  action creates a false active Execute surface after success.
- Reloading before final assertions exercises the reconstructed browser surface
  rather than trusting transient in-memory UI state.
- The final assertions inspect observable UI outcomes and are not tautological,
  deletion-only, prose pins, or implementation mirrors.
- The added autonomy/execution assertions distinguish Human approval from their
  fallback values and therefore exercise the stated anti-auto-approval rule.
- No production extraction, parser, normalization, abstraction, or dependency
  was introduced. No new type escape hatch or error swallowing appears.
- The conditional dismissal before the FAIL screenshot is evidence hygiene:
  it exposes the mission status while leaving the active repair decision intact.

No slop or programming finding violates a Task 3 success criterion.

## checked artifact paths

- `.omo/plans/agent-lab-ux-flow-alignment-roadmap.md`
- `.agent-lab/PROJECT.md`
- `web/e2e/agent-lifecycle-journey.spec.ts`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/single-active-decision-queued.png`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/happy-final-pass.png`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/repair-oracle-fail.png`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/repair-final-pass.png`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/exact-final-command.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/exact-final-command.exit`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/flaky-repeat-3x.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/flaky-repeat-3x.exit`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/prettier-check.log`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/task-3-manual-qa.md`

## exact evidence gaps / notes

- NOTE: `task-3-manual-qa.md` predates the 00:36 replacement PNGs and still
  describes stale Execute controls that are no longer present. Its verdict and
  artifact descriptions should be refreshed before it is used as the canonical
  QA handoff, but the stale prose does not negate the directly inspected PNGs
  or the post-fix 15/15 repeat run.
- NOTE: no current Task 3 code-review report explicitly records the
  `remove-ai-slops`/`programming` perspectives. The direct pass above covers the
  current one-file test diff, so this is not a criterion-linked blocker.
- NOTE: `prettier-check.exit` contains `1` although its log says all matched
  files use Prettier style and `git diff --check` is clean. This metadata
  inconsistency should be regenerated, but Task 3's exact final browser command
  exit is `0`, the repeat run is 15/15, and formatting is not a stated Task 3
  acceptance blocker.
- The ULW status command returned `ULW_LOOP_PLAN_MISSING`; this report therefore
  uses the required fallback evidence location.
