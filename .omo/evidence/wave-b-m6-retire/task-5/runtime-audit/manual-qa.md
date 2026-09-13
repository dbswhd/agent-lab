# Final runtime audit — exact SHA

Pinned worktree: `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-final4`  
Exact SHA: `611a57da35bf1f55214b43bac19cce33b0acd9f5`

Interpretation: PASS means the suspected unsafe behavior was not observed and the safety invariant held.

## manualQa

### surfaceEvidence

| Scenario | Criterion reference | Surface | Exact invocation | Verdict | Artifact refs |
|---|---|---|---|---|---|
| H1 | Browser completion requires Oracle PASS | Headed Chromium lifecycle UI, Oracle FAIL branch | `npm --prefix web run test:e2e -- e2e/agent-lifecycle-journey.spec.ts --headed --reporter=line` | PASS — 6 passed; Oracle FAIL remained `REPAIRING`, showed `Oracle 재검증`, and only the later Oracle PASS path showed completion | A2, A3 |
| H2 | Readiness authority boundary | Readiness CLI + generated packet | `python scripts/dogfood_readiness_report.py --manifest docs/evidence/dogfood-readiness/manifest.json --out-dir /tmp/agent-lab-dogfood-readiness-runtime-audit` | PASS — output `readiness=OPEN`; packet `live.sample_size=0`, `default_change_authorized=false` | A1 |
| H3 | Decision Queue terminal idempotence | Headed Chromium stale-answer flow and Python decision API tests | `npm --prefix web run test:e2e -- e2e/agent-lifecycle-journey.spec.ts --headed --reporter=line`; `PYTHONPATH=src pytest -q tests/test_decision_queue.py tests/test_human_inbox.py::test_inbox_api_resolve_rejects_stale_expected_version tests/test_mission_kernel.py::test_stale_expected_version_is_rejected` | PASS — duplicate stale resolve returned HTTP 409 with `stale_answer`; durable version stayed 8; Python guard suite 7 passed | A2, A4 |
| H4 | Cleanup / provenance | Worktree, process and port checks | `git rev-parse HEAD`; `pgrep -af 'vite|playwright'`; `lsof -nP -iTCP:4173 -sTCP:LISTEN`; `lsof -nP -iTCP:5173 -sTCP:LISTEN` | PASS — exact SHA retained; no Vite/Playwright process or 4173/5173 listener after cleanup | A5 |

### adversarialCases

| Scenario | Criterion reference | Adversarial class | Expected behavior | Verdict | Artifact refs |
|---|---|---|---|---|---|
| ADV-H1 | Oracle-gated completion | misleading_success_output | Merge/diff success with Oracle FAIL must not render terminal success | PASS — fixture stayed REPAIRING with pending action until Oracle PASS | A2, A3 |
| ADV-H2 | Live readiness gate | misleading_success_output / live n=0 | Browser/mock PASS must not authorize default routing without live evidence | PASS — `OPEN`, live `n=0`, authorization false | A1 |
| ADV-H3 | Queue optimistic locking | stale_state / duplicate_action | Replayed old answer must be rejected and must not mutate terminal state | PASS — 409 `stale_answer`, current version 8, exactly two resolve requests (first valid, second rejected) | A2, A4 |
| ADV-H4 | Test/runtime hygiene | mid_operation_interrupt | Browser server and temporary runtime resources must be gone after run | PASS — no process/listener; temporary install/output removed | A5 |

### artifactRefs

| ID | Kind | Description | Path |
|---|---|---|---|
| A1 | text | Exact SHA and readiness packet fields from live `n=0` manifest | `.omo/evidence/wave-b-m6-retire/task-5/final5-qa-retry/runtime-audit/readiness-runtime.txt` |
| A2 | text | Headed Chromium lifecycle run (`6 passed`) | `.omo/evidence/wave-b-m6-retire/task-5/final5-qa-retry/runtime-audit/agent-lifecycle-headed.txt` |
| A3 | image | Oracle FAIL screenshot showing REPAIRING / Oracle reverify action | `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/default-repeat-0-Oracle-FAIL-repairs-through-bounded-re-discuss-retries-before-PASS-repair-oracle-fail.png` |
| A4 | text | Python decision/optimistic-lock checks (`7 passed`) | `.omo/evidence/wave-b-m6-retire/task-5/final5-qa-retry/runtime-audit/decision-queue-python.txt` |
| A5 | text | Post-run cleanup/provenance capture | `.omo/evidence/wave-b-m6-retire/task-5/final5-qa-retry/runtime-audit/cleanup-runtime.txt` |

Overall verdict: **PASS**. All three unsafe-behavior hypotheses were refuted by runtime evidence at the exact requested SHA. Live operational readiness remains **OPEN (`n=0`)**.
