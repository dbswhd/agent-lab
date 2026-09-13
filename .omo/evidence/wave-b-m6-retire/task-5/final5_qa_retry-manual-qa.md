# Manual QA — final5 exact-SHA retry

Pinned worktree: `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-final4`
Exact SHA: `611a57da35bf1f55214b43bac19cce33b0acd9f5`

## manualQa

### surfaceEvidence

| Scenario | Criterion reference | Surface | Exact invocation | Verdict | Artifact refs |
|---|---|---|---|---|---|
| S1 | Exact-SHA readiness retry | CLI readiness packet | `git rev-parse HEAD`; `python scripts/dogfood_readiness_report.py --manifest docs/evidence/dogfood-readiness/manifest.json --out-dir /tmp/agent-lab-dogfood-readiness-final5` | PASS | A1, A2 |
| S2 | Wave B browser contract 4/4 | Playwright Chromium browser UI with mocked API routes | `npm --prefix web run test:e2e -- web/e2e/wave-b-journey.spec.ts` | PASS | A3 |
| S3 | Cleanup / no residue | Worktree and local dev ports | `pgrep -af 'vite|playwright'`; `lsof -nP -iTCP:4173 -sTCP:LISTEN`; `lsof -nP -iTCP:5173 -sTCP:LISTEN`; `git status --short --untracked-files=all` | PASS | A4 |

### adversarialCases

| Scenario | Criterion reference | Adversarial class | Expected behavior | Verdict | Artifact refs |
|---|---|---|---|---|---|
| A-SHA | Exact pinned revision | stale_state / provenance | QA must run at the requested exact SHA and reject a drifted worktree | PASS | A1 |
| A-READINESS | Readiness authority boundary | misleading_success_output | Browser PASS must not promote live readiness; packet remains `OPEN`, live `n=0`, default change unauthorized | PASS | A2 |
| A-BROWSER | Wave B browser contract | flaky_tests | Four mocked-route scenarios complete with no failed/retried scenario and report `4 passed` | PASS | A3 |
| A-CLEANUP | QA hygiene | mid_operation_interrupt / dirty_worktree | Browser web server exits, test ports are free, and no tracked worktree edits remain | PASS | A4 |

### artifactRefs

| ID | Kind | Description | Path |
|---|---|---|---|
| A1 | text | Exact SHA and clean status capture | `.omo/evidence/wave-b-m6-retire/task-5/final5-qa-retry/sha.txt` |
| A2 | text | Readiness CLI output and parsed authority fields | `.omo/evidence/wave-b-m6-retire/task-5/final5-qa-retry/readiness-cli.txt` |
| A3 | text | Wave B browser contract invocation and 4/4 result | `.omo/evidence/wave-b-m6-retire/task-5/final5-qa-retry/wave-b-browser.txt` |
| A4 | text | Process, port, and worktree cleanup checks | `.omo/evidence/wave-b-m6-retire/task-5/final5-qa-retry/cleanup.txt` |

Overall verdict: PASS. Live operational readiness remains OPEN (`n=0`); this retry only confirms the readiness CLI and mocked Wave B browser contract at the pinned SHA.
