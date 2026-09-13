# F3 final manual QA

## Result

PASS — all requested browser journeys passed on fresh isolated ports at SHA `01431f27a875ff0582a5d9e3f6905432eb0627c4`.

## manualQa

### surfaceEvidence

| scenario id | criterion reference | surface | exact invocation | verdict | artifactRefs |
|---|---|---|---|---|---|
| F3-GOLDEN | active Decision Queue CTA → PASS cleanup | Chromium browser UI, Vite `127.0.0.1:43173` | `PLAYWRIGHT_WEB_PORT=43173 npx playwright test e2e/agent-lifecycle-journey.spec.ts --grep='connected Human-gated journey' --trace=on --workers=1` (run in the combined 4-test invocation) | PASS | a1, a5, a13 |
| F3-REPAIR | Oracle FAIL → visible REPAIRING → bounded re-discuss → PASS | Chromium browser UI, Vite `127.0.0.1:43173` | combined lifecycle invocation, test `Oracle FAIL repairs through bounded re-discuss retries before PASS` | PASS | a2, a3, a6, a13 |
| F3-STALE | stale answer returns 409 without state corruption | Chromium browser UI, Vite `127.0.0.1:43173` | combined lifecycle invocation, test `stale expected_version returns 409 without corrupting the resolved state` | PASS | a4, a7, a13 |
| F3-RELOAD | reload resumes same pending operation without duplicate decision | Chromium browser UI, Vite `127.0.0.1:43173` | combined lifecycle invocation, test `reload resumes the same pending operation without duplicating its decision` | PASS | a8, a13 |
| WB-PLAN-REJECT | Wave B plan reject → refine | Chromium browser UI, Vite `127.0.0.1:43174` | `PLAYWRIGHT_WEB_PORT=43174 npx playwright test e2e/wave-b-journey.spec.ts --trace=on --workers=1` | PASS | a9, a13 |
| WB-DIFF-APPROVE | Wave B diff approve resolves pending execution | Chromium browser UI, Vite `127.0.0.1:43174` | same Wave B invocation, `diff approve journey resolves pending execution` | PASS | a10, a13 |
| WB-ORACLE-REPAIR | Wave B Oracle reverify action | Chromium browser UI, Vite `127.0.0.1:43174` | same Wave B invocation, `Oracle repair journey re-verifies failed execution` | PASS | a11, a13 |
| WB-HUMAN-RESUME | Wave B inbox answer resumes flow | Chromium browser UI, Vite `127.0.0.1:43174` | same Wave B invocation, `human resume journey answers inbox question` | PASS | a12, a13 |

### adversarialCases

| scenario id | criterion reference | adversarial class | expected behavior | verdict | artifactRefs |
|---|---|---|---|---|---|
| F3-ADV-ONE-CTA | F3-GOLDEN / F3-STALE | duplicate/stale decision rendering | exactly one `[data-active-decision-id]` and one actionable CTA; queue count may retain queued items | PASS | a2, a4, a7 |
| F3-ADV-NO-EXECUTE-AFTER-PASS | F3-GOLDEN / F3-REPAIR | stale Execute CTA after PASS | after Oracle PASS, no active decision, no `Execute 승인 필요`, and no exact `Execute` button remain | PASS | a1, a3, a5, a6 |
| F3-ADV-FAIL-REPAIRING | F3-REPAIR | false success on Oracle FAIL | FAIL remains visibly `REPAIRING`/`수정 중`, keeps one repair CTA, and does not close the queue | PASS | a2, a6 |
| F3-ADV-STALE-409 | F3-STALE | stale expected-version replay | second answer with old version returns HTTP 409 (`stale_answer`); durable version remains 8 and no duplicate resolution occurs | PASS | a4, a7 |
| F3-ADV-RELOAD-NODUP | F3-RELOAD | reload/replay | reload rehydrates the same pending decision and emits no side-effect POST | PASS | a8 |
| WB-ADV-REQUEST-SINGLETONS | Wave B | route/action duplication | each Wave B action emits exactly one expected POST and no unrelated action endpoint | PASS | a9, a10, a11, a12 |

### artifactRefs

| id | kind | description | path |
|---|---|---|---|
| a1 | screenshot | Golden final PASS surface | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/default-repeat-0-connected-Human-gated-journey-reaches-PASS-only-with-durable-evidence-happy-final-pass.png` |
| a2 | screenshot | Oracle FAIL visibly REPAIRING with reverify CTA | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/default-repeat-0-Oracle-FAIL-repairs-through-bounded-re-discuss-retries-before-PASS-repair-oracle-fail.png` |
| a3 | screenshot | Oracle repair final PASS surface | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/default-repeat-0-Oracle-FAIL-repairs-through-bounded-re-discuss-retries-before-PASS-repair-final-pass.png` |
| a4 | screenshot | Single active decision with queued count 2 | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/default-repeat-0-stale-expected-version-returns-409-without-corrupting-the-resolved-state-single-active-decision-queued.png` |
| a5 | trace | Golden Chromium trace | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/final-f3-qa/traces/lifecycle/golden-pass.trace.zip` |
| a6 | trace | Oracle FAIL → repair → PASS Chromium trace | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/final-f3-qa/traces/lifecycle/oracle-fail-repair.trace.zip` |
| a7 | trace | Stale 409 Chromium trace | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/final-f3-qa/traces/lifecycle/stale-409.trace.zip` |
| a8 | trace | Reload/no-duplicate Chromium trace | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/final-f3-qa/traces/lifecycle/reload-no-duplicate.trace.zip` |
| a9 | trace | Wave B plan reject trace | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/final-f3-qa/traces/wave-b/plan-reject.trace.zip` |
| a10 | trace | Wave B diff approve trace | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/final-f3-qa/traces/wave-b/diff-approve.trace.zip` |
| a11 | trace | Wave B Oracle repair trace | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/final-f3-qa/traces/wave-b/oracle-repair.trace.zip` |
| a12 | trace | Wave B Human resume trace | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/final-f3-qa/traces/wave-b/human-resume.trace.zip` |
| a13 | log | Exact commands, results, trace inspection, and cleanup receipt | `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-review/.omo/evidence/final-f3-qa/f3-run-log.md` |
