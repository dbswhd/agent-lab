# Todo 2 — classification-independent Wave B navigation

Recorded: 2026-07-23T17:34:53Z  
Commit: `17ef052ecd264d9c99ca9b60b9fe5d4ccca6ec5d`

## Change

The sole committed change is `web/e2e/wave-b-journey.spec.ts`: its mocked API route now matches `/api/` by URL pathname rather than the literal `http://127.0.0.1:4173` origin. This lets the browser fixture use Playwright's isolated `PLAYWRIGHT_WEB_PORT` without changing production code or relying on an existing server.

Historical baseline, red-first, and shared-worktree-blocker records remain in sibling Task 2 artifacts and are summarized in `task-2.json`. They are context only; the current-HEAD proof is the fresh raw output below.

## Final-run provenance

The post-run runner snapshot is retained at `task-2-final/raw/profile-flags-fixtures-snapshot.log`.

- `AGENT_LAB_RUN_PROFILE`, Mission UI-read-model, Mission-authority, authority-cohort, dual-write, and dual-write-cohort shell variables were all `<unset>`.
- The repository resolver defaults an empty run-profile input to `balanced`; the source excerpt is `task-2-final/raw/run-profile-default-source.log`. This fixture does not start that backend resolver: it runs with `VITE_SKIP_API=1` and fulfills `/api/` in Playwright, so `balanced` is recorded as repository-default provenance rather than a browser-test behavior claim.
- The browser-observed mock `GET /api/health/flags` payload contains exactly `AGENT_LAB_MISSION_UI_READ_MODEL=1`, despite the shell variable being unset.
- There is no live authority cohort: authority-related variables are unset and the test is fully mocked. The fixture session IDs are `wave-b-active-plan-reject`, `wave-b-plan-reject`, `wave-b-diff-approve`, `wave-b-oracle-repair`, and `wave-b-human-resume`.

## Current verification

| Scenario | Invocation | Exit | Binary observable | Raw artifact |
| --- | --- | ---: | --- | --- |
| Exact isolated suite | `cd web && PLAYWRIGHT_WEB_PORT=4301 npx playwright test e2e/wave-b-journey.spec.ts --workers=1 --reporter=line` | 0 | 4 passed | `task-2-final/raw/exact-wave-b-4301-rerun.log` |
| Repeat stability | `cd web && PLAYWRIGHT_WEB_PORT=4302 npx playwright test e2e/wave-b-journey.spec.ts --workers=1 --reporter=line --repeat-each=3` | 0 | 12 passed | `task-2-final/raw/repeat-each-3-wave-b-4302.log` |
| Relevant unit suite | `cd web && npm run test -- --run src/utils/dogfoodSessions.test.ts` | 0 | 43 files / 185 tests passed | `task-2-final/raw/relevant-unit-dogfood-sessions-rerun.log` |
| Web build | `cd web && npm run build` | 0 | TypeScript + Vite build passed | `task-2-final/raw/web-build-rerun.log` |

## Manual browser QA

The scoped plan-reject trace starts with the Korean-topic Active fixture and then selects the ASCII Dogfood fixture. In each state `openSession()` asserts the exact stable `session-${sessionId}` row has `aria-current="true"`, before the scenario asserts its first decision surface, `.plan-approval-strip`, is visible.

- Trace: `task-2-final/manual/wave-b-journey-plan-reject-1fb8b-est-and-enters-refine-phase/trace.zip`
- Assertion event extraction: `task-2-final/raw/manual-trace-navigation-assertions.log`
- Active screenshot: `task-2-final/screenshots/active-selected-plan-approval.jpeg`
- Dogfood screenshot: `task-2-final/screenshots/dogfood-selected-plan-approval.jpeg`

Visual inspection confirms the Active screenshot displays the Korean row with Sessions selected and the plan-approval surface, while the Dogfood screenshot displays `Wave B plan reject` with Dogfood selected and the same surface.

## Adversarial checks and cleanup

- `stale_state`: both scopes are selected in one fresh browser scenario by stable ID, not label text.
- `flaky_tests`: separate free ports produced 4/4 and 12/12.
- `misleading_success_output`: trace assertion events, trace archive, and two extracted screenshots align to the same manual run.
- `dirty_worktree`: the final commit contains only the owned spec; concurrent files were not reverted or staged.
- Port receipts confirm no listener remained at 4301, 4302, or 4303 after the runs. `.venv` and `.debug-journal.md` were preserved because ownership could not be proven.

The earlier failed capture wrappers are disclosed in `task-2.json` and are not counted as proof. The build’s Vite chunk-size advisory remains visible in the raw build log; it is unrelated to this test-only change.
