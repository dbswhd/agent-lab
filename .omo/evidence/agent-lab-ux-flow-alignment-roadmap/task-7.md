# Task 7 — dogfood readiness and repair-loop measurement

Status: **OPEN**  
Commits: `499f19b810c40a175c5d1e553f9865a7ddde53cf`,
`01431f27a875ff0582a5d9e3f6905432eb0627c4`  
Evidence directory: `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/`

## Readiness packet

- Scenario: separate mock, browser, and live evidence and fail closed.
- Invocation: `make dogfood-readiness-report MANIFEST=.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7/manifest.json OUT_DIR=.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-7`
- Binary observable: exit `0`; packet status `OPEN`; `default_change_authorized=false`.
- Artifacts: `dogfood-readiness.json`, `dogfood-readiness.md`, `readiness-cli.txt`, `manifest.json`.

Measured result: mock `PASS` (n=2), browser `PASS` (Wave B n=4), live `OPEN`
(n=0). Oracle coverage is `1.0`; false-success count is `1`; repair attempts
are `1`; FAIL→repair→PASS chains are `1`; retry plateau count is `0`; gate
latency is `3.0s`; cohort/non-cohort parity is unavailable (`null`, n=0/0).
F7, N4-D3, and HS-M5 are each `OPEN` with an owner and next gate in the packet.

## Preserved session artifacts

- Success scenario: `sessions/_regression/worktree_merge_ok/run.json`.
  Observable: final mock Oracle verdict `pass`.
- Failure/repair scenario: `sessions/_regression/execute_verify_loop/run.json`.
  Observable: verify history `fail → pass`, one repair attempt, final Oracle
  verdict `pass`.

These are mock regression evidence only. No live claim is inferred from them.

## Verification

- Focused report/dogfood tests:
  `.venv/bin/pytest tests/test_dogfood_readiness_report.py tests/test_f7_dogfood_report.py tests/test_dogfood_track.py tests/test_feedback_report.py tests/test_run_dogfood_suite.py -q`
  → `54 passed`; artifact `post-commit-focused-tests.txt`.
- Wave B browser:
  `cd web && npx playwright test e2e/wave-b-journey.spec.ts --reporter=line`
  → `4 passed`; artifact `wave-b-browser.txt`. API calls are mocked, so this is
  browser evidence, not live evidence.
- Web unit tests: `cd web && npm test` → `185 passed`; artifact `web-tests.txt`.
- Web build: `cd web && npm run build` → exit `0`; artifact `web-build.txt`.
- Smoke: `make smoke` → 38 regression + 3 example missions pass; artifact
  `smoke.txt`.
- Cleanup: no listener on Playwright port 4173; artifact `process-cleanup.txt`.
- `make test-fast` completed red: `3577 passed, 1 skipped, 21 failed, 2 errors`.
  The captured failures include shared-worktree Task 5/6 import visibility,
  pre-existing structure/UI ratchets, and shared-venv mypy ratchets. No
  unrelated baseline or concurrent code was changed. Artifact `test-fast.txt`.

## Open gates

- Live success and FAIL→repair/re-discuss sessions: owner Agent Lab dogfood
  operator; next gate is a credentialed supervisor run with raw session paths.
- Cohort parity: owner Agent Lab dogfood operator; next gate is non-zero
  cohort and non-cohort samples from the same window.
- F7: collect ≥10 instrumented sessions at ≥70% repo-map coverage and record
  Human ON/OFF.
- N4-D3: collect ≥10 live outcomes for each L0–L3 level.
- HS-M5: preserve one addressable pattern and one live Human-approved merge.
- Full fast gate: owner integration lead; next gate is to integrate concurrent
  Task 5/6 changes and reconcile shared baselines, then rerun `make test-fast`.

## Fail-closed verifier repair

- Scenario: a `live` PASS with `sample_size=0` and a browser-only artifact is
  rejected before aggregation.
- Invocation: `.venv/bin/pytest tests/test_dogfood_readiness_report.py -q`.
- Binary observable: `5 passed`; both zero-sample and browser-only live PASS
  fixtures raise validation errors.
- Artifacts: `red-fail-closed.txt`, `fail-closed-tests.txt`,
  `fail-closed-ruff.txt`, `fail-closed-packet.txt`.
- Packet guard: zero live sample independently rolls the live tier to `OPEN`.
  A valid live PASS must reference a `run.json` with a non-mock Oracle source
  and pass/fail verdict.
