# Task 3 manual QA — current post-fix handoff

Recorded at `2026-07-23T18:03:02Z` against exact source SHA
`f60e3b35e8645b0f3611cf115f2195925ce1650d` in the isolated worktree
`/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment`.

This is a frontend browser/render/request/read-model/SSE-shaped fixture check.
It does not claim production backend auth, durable storage, real route side
effects, restart durability, or authority; those checks belong to Task 6.

## Current lane results

| Scenario | Exact invocation | Binary observable | Verdict | Persisted artifact |
|---|---|---|---|---|
| Connected golden lifecycle | `cd /Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/web && PLAYWRIGHT_WEB_PORT=4283 npx playwright test e2e/agent-lifecycle-journey.spec.ts --reporter=line` | 6 passed; Human gates, Oracle PASS/FAIL repair, stale 409, reload, dirty/malformed guards | PASS | [lifecycle.log](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/code-lane-repair/lifecycle.log) |
| Repeat/flake check | `PLAYWRIGHT_WEB_PORT=4293 npx playwright test e2e/agent-lifecycle-journey.spec.ts --repeat-each=3 --workers=1 --reporter=line` | 18 passed; 16 repeat-indexed screenshots are nonempty | PASS | [lifecycle-repeat-3.log](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/code-lane-repair/lifecycle-repeat-3.log), [screenshot-inventory.txt](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/security-context-fix/screenshot-inventory.txt) |
| Affected nondefault-port specs | `PLAYWRIGHT_WEB_PORT=4297 npx playwright test e2e/mission-read-model-parity.spec.ts e2e/ui-simplification.spec.ts e2e/plan-approval.spec.ts --workers=1 --reporter=line` | 17 passed | PASS | [affected-nondefault.log](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/code-lane-repair/affected-nondefault.log) |
| Full nondefault E2E | `PLAYWRIGHT_WEB_PORT=4301 npx playwright test --reporter=line` | 27 passed | PASS | [all-e2e.log](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/code-lane-repair/all-e2e.log) |
| Web unit suite | `npm test` | 43 files / 185 tests passed | PASS | [unit.log](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/code-lane-repair/unit.log) |
| Build/type-check | `npm run build` | tsc and Vite completed; 347 modules transformed | PASS | [build.log](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/code-lane-repair/build.log) |
| Formatting/diff | `npx prettier --check e2e/agent-lifecycle-journey.spec.ts playwright.config.ts; git diff --check` | all matched files pass; `diff_check=pass` | PASS | [prettier.log](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/code-lane-repair/prettier.log), [diff-check.log](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/code-lane-repair/diff-check.log) |
| Invalid-port fail-closed | Config probes for injection, zero, high, and alpha port values | all four statuses 1; `marker_created=no` | PASS | [port-validation-probe.log](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/raw/security-context-fix/port-validation-probe.log) |

## Visual and trace checks

- [single-active-decision-queued.png](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/single-active-decision-queued.png) shows one expanded decision CTA with one queued item.
- [happy-final-pass.png](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/happy-final-pass.png) and [repair-final-pass.png](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/repair-final-pass.png) show Oracle PASS/completion with no active decision or execute CTA.
- [repair-oracle-fail.png](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/browser/repair-oracle-fail.png) shows the repair state and Oracle FAIL before bounded re-discuss.
- [happy-journey-trace.zip](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/traces/happy-journey-trace.zip), [repair-journey-trace.zip](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/traces/repair-journey-trace.zip), and [stale-version-trace.zip](/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-alignment/.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-3/traces/stale-version-trace.zip) are nonempty persisted browser traces.

The request-contract assertion is included in the six-test lifecycle run: it
checks no gate POST before a rendered Human action, one normal product POST per
Human click, and no automatic/trust-budget transition. The log records the
test pass rather than duplicating those internal assertion counts.

## Historical reports and supersession

The earlier clean-start report and review were produced before the repaired
web-server/fixture lane and used pre-fix SHAs. Their FAIL or review-in-progress
observations remain useful history but are not the current verdict. The
exact-SHA post-fix evidence above supersedes them; no historical file was
edited in place.

## Watch item

The fixture/spec is approximately 1,544 pure LOC and mirrors lifecycle state
for browser coverage. This is a LOW maintenance/drift watch, not a production
authority or durability result. Task 6 remains responsible for real disposable
repository routes, restart/rollback, and persistence.

**Current verdict: PASS_WITH_EXPLICIT_SCOPE.**
