# F2 code-quality review

- Reviewed SHA: `01431f27a875ff0582a5d9e3f6905432eb0627c4`
- Baseline: `dca996c0`
- Scope: routing/promotion evidence, Mission-authority cohort scripts and routes, Human Inbox projection, Playwright configuration and E2E/docs.
- Skill-perspective check: ran. Consulted `omo:programming` (including Python and TypeScript references) and `omo:remove-ai-slops`. The production diff has no blocking violation of either perspective. The deliberately large E2E fixture/module is deferred module/bundle hardening and is nonblocking per the review scope.

## CRITICAL

None.

## HIGH

None.

## MEDIUM

None that block this goal.

## LOW

None.

## Verification and evidence assessment

- Pinned HEAD resolves exactly to the requested SHA; `git diff --check dca996c0..01431f27a875ff0582a5d9e3f6905432eb0627c4` is clean.
- Inspected the supplied task-5 evidence artifacts and their paths. They identify concrete commands and outputs, including the red collection failure, focused regression suites, lint, and deterministic stale/malformed promotion probes. They are historical evidence, not accepted merely on assertion.
- Local re-execution could not proceed: this worktree has no `.venv/bin/python` or `.venv/bin/pytest`; `make test-fast` fails before tests at the missing interpreter. This is an environment limitation, not a code failure.
- The promotion logic is fail-closed for insufficient, stale, malformed, unsafe, low-parity, or unavailable-latency data. Its green state remains `HUMAN_GO_REQUIRED`; it does not modify runtime mode.
- Mission-authority route probing uses temporary roots/cohort allowlists and validates duplicate/stale rejection plus legacy fallback. The real HTTP harness kills its disposable server process in `finally` blocks.
- Human Inbox projects exactly one actionable decision and reports the remainder as queued. The new unit test asserts visible behavior rather than copied implementation constants. No deletion-only, tautological, or prose/prompt tests were found in the reviewed additions.

## Decision

- `codeQualityStatus`: WATCH
- `recommendation`: APPROVE
- `blockers`: none

`WATCH` reflects only the unavailable local test interpreter and the explicitly deferred oversized E2E/module hardening; neither is a MAJOR/CRITICAL issue for this goal.
