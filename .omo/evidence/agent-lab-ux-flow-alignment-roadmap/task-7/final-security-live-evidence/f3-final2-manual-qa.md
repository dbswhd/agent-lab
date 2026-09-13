# F3 final manual QA

Exact SHA: `5677b7ea881a4bfd3c55fa57c1a97f1296d42df4`

Overall verdict: **FAIL — browser lifecycle and Wave B are green, but the checked-in readiness packet is stale/not reproducibly runnable at this SHA.** Its inspected values are `readiness=OPEN`, `live n=0`, and `default_change_authorized=false`, but the packet embeds commit `01431f27a875ff0582a5d9e3f6905432eb0627c4` and the referenced `task-7/manifest.json` is absent, so a fresh report invocation fails.

## manualQa

### surfaceEvidence

| scenario id | criterion reference | surface | exact invocation | verdict | artifactRefs |
|---|---|---|---|---|---|
| F3-S1 | happy lifecycle / one contextual primary CTA / clean PASS | isolated Chromium browser, lifecycle fixture `happy` | `PLAYWRIGHT_WEB_PORT=4373 npx playwright test e2e/agent-lifecycle-journey.spec.ts --grep 'connected Human-gated journey|frontend mock contract|Oracle FAIL repairs|stale expected_version' --workers=1 --reporter=line` | PASS | `A1`, `A3` |
| F3-S2 | Oracle FAIL must remain repairing, then bounded retry reaches PASS | isolated Chromium browser, lifecycle fixture `repair` | `PLAYWRIGHT_WEB_PORT=4373 npx playwright test e2e/agent-lifecycle-journey.spec.ts --grep 'connected Human-gated journey|frontend mock contract|Oracle FAIL repairs|stale expected_version' --workers=1 --reporter=line` | PASS | `A1`, `A4`, `A5` |
| F3-S3 | stale expected_version returns 409 without corrupting resolved state | isolated Chromium browser, lifecycle fixture `stale` | `PLAYWRIGHT_WEB_PORT=4373 npx playwright test e2e/agent-lifecycle-journey.spec.ts --grep 'connected Human-gated journey|frontend mock contract|Oracle FAIL repairs|stale expected_version' --workers=1 --reporter=line` | PASS | `A1`, `A6` |
| F3-S4 | Wave B plan reject, diff approve, Oracle repair, Human resume | isolated Chromium browser, Wave B mocked-route journeys | `PLAYWRIGHT_WEB_PORT=4374 npx playwright test e2e/wave-b-journey.spec.ts --workers=1 --reporter=line` | PASS | `A2` |
| F3-S5 | current readiness packet reports OPEN/live n=0/default false at this SHA | readiness artifact inspection plus attempted report invocation | `/Users/yoonjong/Projects/agent-lab/.venv/bin/python -c 'parse checked-in .../current-packet/dogfood-readiness.json and print readiness/live/default fields'`; then `/Users/yoonjong/Projects/agent-lab/.venv/bin/python scripts/dogfood_readiness_report.py --manifest .omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/manifest.json --out-dir /tmp/f3-current-packet` | FAIL (fresh invocation blocked: manifest absent; checked-in packet is stale commit) | `A7`, `A8` |

### adversarialCases

| scenario id | criterion reference | adversarial class | expected behavior | verdict | artifactRefs |
|---|---|---|---|---|---|
| F3-A1 | Oracle FAIL repair safety | false-success / bounded-retry | Oracle FAIL remains `REPAIRING`, keeps one active decision, and only attempt two PASS closes it | PASS | `A1`, `A4`, `A5` |
| F3-A2 | stale decision safety | stale-version replay | stale `expected_version=7` receives 409 and does not duplicate/corrupt the resolved decision | PASS | `A1`, `A6` |
| F3-A3 | Human authority boundary | auto-approval / side-effect injection | rendered Human actions emit normal gate requests; `approved_by` remains human and no auto-merge/trust-budget fields are emitted | PASS | `A1`, `A3` |
| F3-A4 | rollout safety | default/authority promotion | readiness remains OPEN with live sample `0` and `default_change_authorized=false`; no UI claim authorizes default routing/authority | FAIL (values observed, but current packet is bound to old commit and cannot be freshly regenerated because manifest is absent) | `A7`, `A8` |

### artifactRefs

| id | kind | description | path |
|---|---|---|---|
| A1 | command log | Fresh lifecycle Playwright run, 4 passed, exact SHA and invocation | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-lifecycle-playwright.txt` |
| A2 | command log | Fresh Wave B Playwright run, 4 passed, exact SHA and invocation | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-wave-b-playwright.txt` |
| A3 | screenshot | Happy final PASS, 1280×800; merged checks/Oracle pass and no active decision | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/default-repeat-0-connected-Human-gated-journey-reaches-PASS-only-with-durable-evidence-happy-final-pass.png` |
| A4 | screenshot | Oracle FAIL repair state, 1280×800; visible fail context and `Oracle 재검증` | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/default-repeat-0-Oracle-FAIL-repairs-through-bounded-re-discuss-retries-before-PASS-repair-oracle-fail.png` |
| A5 | screenshot | Final repair PASS, 1280×800; clean merged state after bounded retry | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/default-repeat-0-Oracle-FAIL-repairs-through-bounded-re-discuss-retries-before-PASS-repair-final-pass.png` |
| A6 | screenshot | Stale fixture, 1280×800; single active question and no legacy duplicate resolve row | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/default-repeat-0-stale-expected-version-returns-409-without-corrupting-the-resolved-state-single-active-decision-queued.png` |
| A7 | packet JSON | Checked-in readiness packet values: OPEN, live OPEN n=0, default false; packet commit is old `01431f27...` | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/current-packet/dogfood-readiness.json` |
| A8 | command log | Readiness inspection plus failed fresh report invocation and port cleanup receipt | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-readiness-observable.txt` |

Cleanup: Playwright web servers on ports 4373 and 4374 exited; `lsof` found no listeners. No product source or test files were edited.
