# F3 manual QA — exact SHA `9a323834bf169533406e4fe0a36a56e2684336dd`

All browser invocations used fresh Playwright processes with isolated Vite ports (`4317` for lifecycle and `4318` for Wave B). API responses were fixture-routed by the tracked browser specs; this is browser-contract evidence, not credentialed live readiness evidence.

## manualQa

### surfaceEvidence

| scenario id | criterion reference | surface | exact invocation | verdict | artifactRefs |
|---|---|---|---|---|---|
| F3-readiness | F3 operational readiness guard | tracked CLI | `PYTHONPATH=src /Users/yoonjong/Projects/agent-lab/.venv/bin/python scripts/dogfood_readiness_report.py --manifest docs/evidence/dogfood-readiness/manifest.json --out-dir <temp>` from clean checkout | PASS: exit `0`, `readiness=OPEN`, `evidence_by_tier.live.sample_size=0`, `evidence_by_tier.live.status=OPEN`, `default_change_authorized=false` | `A1`, `A2`, `A3` |
| F3-lifecycle-happy | F3 lifecycle happy path | real browser UI | `PATH=/Users/yoonjong/Projects/agent-lab/web/node_modules/.bin:$PATH PLAYWRIGHT_WEB_PORT=4317 /Users/yoonjong/Projects/agent-lab/web/node_modules/.bin/playwright test e2e/agent-lifecycle-journey.spec.ts --grep 'connected Human-gated journey reaches PASS only with durable evidence' --reporter=line` | PASS: 1 test passed; rendered Human approval flow reaches Oracle PASS and final surface has no active decision/execute CTA | `A4`, `A5` |
| F3-lifecycle-repair | F3 Oracle FAIL → bounded repair → PASS | real browser UI | same Playwright binary, port `4317`, `--grep 'Oracle FAIL repairs through bounded re-discuss retries before PASS'` | PASS: 1 test passed; repair CTA is visible after FAIL, attempt one remains REPAIRING, attempt two reaches PASS | `A6`, `A7`, `A8` |
| F3-lifecycle-stale | F3 stale decision protection | real browser UI | same Playwright binary, port `4317`, `--grep 'stale expected_version returns 409 without corrupting the resolved state'` | PASS: 1 test passed; duplicate stale answer returns `409 stale_answer`, durable version remains `8` | `A9`, `A10` |
| F3-wave-b | Wave B read-model UI contract | real browser UI | `PATH=/Users/yoonjong/Projects/agent-lab/web/node_modules/.bin:$PATH PLAYWRIGHT_WEB_PORT=4318 /Users/yoonjong/Projects/agent-lab/web/node_modules/.bin/playwright test e2e/mission-read-model-parity.spec.ts --reporter=line` | PASS: 9/9 tests passed; migrated/legacy/error/disconnect/stale/terminal/missing/pause states exercised; question CTA and options visibly rendered | `A11`, `A12` |

### adversarialCases

| scenario id | criterion reference | adversarial class | expected behavior | verdict | artifactRefs |
|---|---|---|---|---|---|
| ADV-stale | F3 stale decision protection | stale_state | stale `expected_version` must be rejected without changing resolved state | PASS: `409`, `stale_answer`, current version `8` | `A9`, `A10` |
| ADV-repair | F3 Oracle repair semantics | misleading_success_output | Oracle FAIL must not count as success; repair remains actionable until PASS | PASS: repair screenshot shows `Oracle 재검증`; test asserts REPAIRING/attempt 1 before final PASS | `A6`, `A7` |
| ADV-waveb-fallback | Wave B read-model fallback | stale_state | stale/missing/terminal joins must not expose a phantom legacy resolve control | PASS: 9/9 Wave B tests, including stale/missing/terminal cases | `A11`, `A12` |
| ADV-dirty | F3 clean-checkout provenance | dirty_worktree | exact checked-out SHA must remain unchanged after QA | PASS: `git rev-parse HEAD` remains `9a323834bf169533406e4fe0a36a56e2684336dd`; only ignored/untracked evidence was written | `A13` |
| ADV-malformed | F3 browser lifecycle scope | malformed_input | not applicable: requested scenarios use typed fixture routes; malformed-payload coverage is outside these browser invocations | not_applicable — one-line reason above | `A4`, `A11` |

## artifactRefs

| id | kind | description | path |
|---|---|---|---|
| A1 | cli-log | readiness CLI stdout/stderr | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/readiness-cli.txt` |
| A2 | json | generated readiness packet with live `n=0` and default false | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/dogfood-readiness.json` |
| A3 | exit-code | readiness CLI exit code `0` | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/readiness-cli.exit` |
| A4 | browser-log | lifecycle happy Playwright transcript | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/lifecycle-happy.txt` |
| A5 | screenshot | lifecycle final Oracle PASS surface | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/happy-pass.png` |
| A6 | browser-log | lifecycle repair Playwright transcript | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/lifecycle-repair.txt` |
| A7 | screenshot | Oracle FAIL repair CTA surface | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/repair-fail-cta.png` |
| A8 | screenshot | bounded repair final PASS surface | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/repair-final-pass.png` |
| A9 | browser-log | lifecycle stale Playwright transcript | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/lifecycle-stale.txt` |
| A10 | screenshot | stale decision queue CTA surface | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/stale-cta.png` |
| A11 | browser-log | Wave B Playwright transcript (`9 passed`) | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/wave-b.txt` |
| A12 | screenshot | Wave B migrated question CTA/options surface | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/wave-b-question-cta.png` |
| A13 | git-check | exact SHA and listener cleanup check | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/final-security-live-evidence/f3-manual-qa/cleanup.txt` |
