# Agent Lab decision surface final visual gate review

recommendation: REJECT

visualQAVerdict: REVISE

reviewedAt: 2026-07-12 Asia/Seoul

baseline: `ccdf465bccde18285a927133d3c3261bf7395dba`

reviewedDiffSha256: `981b481a51bd8c0d6135dbc6572dd0c5d800a0e7d1c0bee35f3309db8a5ad92b`

## originalIntent

Perform a final, read-only visual QA of Agent Lab's human decision surface using the latest captures and related source. Judge primary-action hierarchy, blocker adjacency, question option/freeform clarity, 375px usability, and information density; distinguish only what prior findings are resolved versus what remains.

## desiredOutcome

- The current human decision is immediately understandable and has one unmistakable contextual primary action.
- A blocker is shown next to the control it disables and presents a clear next step.
- Question options, recommended state, freeform alternative, selection state, keyboard behavior, and submit readiness are unambiguous.
- At 375px, the active decision and its actions remain readable, unobscured, and horizontally contained.
- Header, body, footer, routing hint, and composer copy each add distinct information rather than repeating the same instruction.
- Current captures, tests, manual QA, code review, and direct slop/programming review support the same completion claim.

## userOutcomeReview

### Resolved from the prior review

- **Primary action hierarchy:** PASS in the supplied resting approval and question captures. `승인하고 실행` is the sole filled primary action, `수정 요청` is secondary, and question `제출` is the sole primary submit control.
- **Blocker adjacency:** PASS in `/tmp/agent-lab-plan-blocked-1280.png` and `/tmp/agent-lab-plan-blocked-375.png`. The objection reason and its `수용`/`기각` resolution controls sit immediately above the disabled approval action.
- **Approval at 375px:** PASS for basic containment and reachability. The workbench is absent, the card and both actions fit without horizontal overflow, and the composer does not cover the approval controls.
- **Question choice/freeform baseline clarity:** PASS at 1440px. Options, recommendation badge, descriptions, `기타 — 직접 입력…`, disabled-submit hint, skip action, and submit action are grouped coherently.
- **Question keyboard semantics:** Improved in source and exercised by E2E. The surface now uses radio semantics and supports arrow navigation plus Home; option selection clears freeform and typing clears selection in production code.

### Remaining

- **Information density and ownership:** REVISE. Approval repeats the same job across `결정 필요 / 계획 검토`, `승인 대기 / 승인하고 실행`, the review-detail sentence, worktree consequence strip, routing hint, and composer placeholder. Question similarly repeats `질문 응답` and `질문에 답해주세요`. This conflicts with `web/DESIGN.md`'s header/body/footer ownership contract and makes one decision read like several nested notices.
- **Question 375px and selected/freeform visual states:** REVISE. The only question capture is the 1440px unselected state. There is no 375px question capture, selected-option capture, or freeform-active capture, so wrapping, footer density, selected contrast, and action reachability are not visually proven at the required mobile width.
- **Execute-failure recovery:** REVISE. `WorkToolPanel.tsx` says execution can be retried but composer mode provides no adjacent retry/jump action. No desktop or mobile recovery capture was supplied. Explanatory copy without the promised action does not complete the decision surface.

## blockers

1. The approval surface still duplicates intent and consequence across the queue header, approval card, routing hint, and composer placeholder. The shipped hierarchy is visually clear, but the information-density criterion is not met.
2. Required 375px question coverage and selected/freeform visual evidence are absent. Desktop unselected evidence cannot establish mobile usability or selected-state clarity.
3. Execute-failure recovery has no action adjacent to its retry explanation and has no current capture.
4. The current UX diff has no matching manual QA matrix, executor evidence bundle, notepad path, or code-review report. The only discovered code-review/manual-QA artifacts are for a different orchestration diff (`084e56a7...`).
5. Direct `remove-ai-slops` review found identical decision-token blocks duplicated in both the light and dark scopes of `web/src/styles/tokens.css`. This unresolved production duplication independently blocks approval.
6. Direct `programming` review found modified production modules above the consulted 250-pure-LOC ceiling (`HumanInboxPanel.tsx` 811, `PlanApprovalStrip.tsx` 260, `WorkToolPanel.tsx` 359) with no size exception, plus an unnecessary fallback after an exhaustive `ComposerStackLane` switch in `DecisionQueueHeader.tsx`.

## directSlopAndOverfitPass

- **Excessive/useless tests:** The responsive loop is useful for width and workbench visibility, but too narrow to prove non-occlusion or clickability. No excessive test volume was found.
- **Deletion-only/removal-only tests:** None added.
- **Tests that merely verify requested removal:** None added.
- **Tautological/implementation-mirroring tests:** The question test checks copy, placeholder, ARIA state, and enabled state but does not submit an option or freeform answer, inspect the payload, verify selection/freeform exclusivity, capture selected state, or exercise the question at 375px. It provides partial confidence only.
- **Unnecessary extraction/parsing/normalization:** No new parser or normalization layer was added. `decisionMeta` is a reasonable mapping, but its default fallback is unreachable under the declared union and weakens exhaustive checking.
- **Production duplication:** FAIL. Light decision tokens are duplicated at `web/src/styles/tokens.css:54-79`; dark decision tokens are duplicated at `:356-380`.
- **Maintenance burden:** FAIL. Three modified production TypeScript components exceed 250 pure LOC without a documented exception.

## codeReviewCoverageCheck

No code-review report for diff `981b481a...` was supplied or found. `.omo/evidence/orchestration-enforcement-code-review.md` reviews another branch and hash and does not cover this UI diff. Therefore required report coverage of the `remove-ai-slops` perspective, overfit criteria, duplicate tokens, responsive visual gaps, recovery adjacency, and oversized modules is absent. This report gap independently requires rejection and does not replace the direct pass above.

## verificationRun

- `npm run test:e2e -- e2e/plan-approval.spec.ts`: 6 passed.
- `npx tsc --noEmit`: passed.
- Targeted `npx eslint ...`: 0 errors, 1 `react-hooks/exhaustive-deps` warning at `HumanInboxPanel.tsx:676`.
- Targeted `npx prettier --check ...`: passed.
- `git diff --check`: passed.

The green E2E result proves the mocked interaction paths it asserts; it does not close the missing visual states or the absent user-action recovery path.

## checkedArtifactPaths

- `/tmp/agent-lab-plan-approval-1280.png` — 1280×900, fresh after relevant source edits.
- `/tmp/agent-lab-plan-approval-768.png` — 768×900, fresh after relevant source edits.
- `/tmp/agent-lab-plan-approval-375.png` — 375×900, fresh after relevant source edits.
- `/tmp/agent-lab-plan-blocked-1280.png` — 1280×800, fresh after relevant source edits.
- `/tmp/agent-lab-plan-blocked-375.png` — 375×900, fresh after relevant source edits.
- `/tmp/agent-lab-plan-question-1440.png` — 1440×900, fresh after relevant source edits.
- `web/DESIGN.md`
- `web/e2e/plan-approval.spec.ts`
- `web/src/components/ComposerDecisionSurface.tsx`
- `web/src/components/ComposerNoticeCard.tsx`
- `web/src/components/DecisionQueueHeader.tsx`
- `web/src/components/HumanInboxPanel.tsx`
- `web/src/components/PlanApprovalStrip.tsx`
- `web/src/components/WorkToolPanel.tsx`
- `web/src/styles/layout.css`
- `web/src/styles/plan-execute.css`
- `web/src/styles/prototype-panels.css`
- `web/src/styles/tokens.css`
- `web/src/i18n/messages.ts`
- `web/src/utils/roomComposerPrefs.ts`
- `.omo/evidence/orchestration-enforcement-code-review.md` — inspected and rejected as unrelated evidence.
- `.omo/evidence/orchestration-hands-on-qa/manual-qa-report.json` — inspected and rejected as unrelated evidence.

## exactEvidenceGaps

- No 375px question screenshot.
- No selected-option screenshot at any width.
- No freeform-active screenshot at any width.
- No execute-failure/recovery screenshot at desktop or mobile width.
- No interaction capture proving mobile action reachability, selected contrast, or option/freeform transition.
- The question E2E does not verify submitted option/freeform payloads or mutual exclusivity.
- The blocked-state test proves DOM visibility and disabled state but not an actual resolution submission.
- No current manual QA matrix, executor evidence bundle, notepad path, or code-review report tied to `981b481a...`.
- No independent dual-oracle visual-QA pass was possible because no subagent tool surface is available in this session.

## scopeSafety

No product source, test, configuration, or supplied capture was modified. Only this required gate-review artifact was added.
