# Task 3 security/context verification

All commands ran from `web/` unless noted.

| Scenario | Invocation | Binary observable | Captured artifact |
|---|---|---|---|
| Human UI happy, Oracle repair/misleading merge output, stale state, dirty worktree, malformed input, reload/interruption, unauthorized plan/merge requests | `PLAYWRIGHT_WEB_PORT=4283 npx playwright test e2e/agent-lifecycle-journey.spec.ts --reporter=line` | `6 passed` | `lifecycle-first-green.log` |
| Flake/repeated interruption and collision-resistant screenshot provenance | `PLAYWRIGHT_WEB_PORT=4293 npx playwright test e2e/agent-lifecycle-journey.spec.ts --repeat-each=3 --workers=1 --reporter=line` | `18 passed`; repeat-indexed nonempty PNGs | `lifecycle-repeat-3.log`, `screenshot-inventory.txt`, `../../browser/default-repeat-*.png` |
| Frontend/mock request contract only | lifecycle frontend mock contract test | no plan/merge POST before rendered actions; exactly one normal product POST after each Human click; no auto/trust-budget request or unsolicited transition | `../code-lane-repair/lifecycle.log` |
| Dynamic API mocks on a fresh nondefault port | `PLAYWRIGHT_WEB_PORT=4297 npx playwright test e2e/mission-read-model-parity.spec.ts e2e/ui-simplification.spec.ts e2e/plan-approval.spec.ts --workers=1 --reporter=line` | `17 passed` | `nondefault-port-affected-specs.log` |
| Full E2E including Wave B on a fresh nondefault port | `PLAYWRIGHT_WEB_PORT=4301 npx playwright test --reporter=line` | `27 passed` | `all-e2e-nondefault.log` |
| Malicious/invalid port config and command injection | config-load probes with `4173;touch <marker>`, `0`, `65536`, `abc` | all exit `1`; `marker_created=no` | `port-validation-probe.log` |
| Classification-independent navigation red at exact source commit | `PLAYWRIGHT_WEB_PORT=4173 npx playwright test ... --grep 'migrated question|plan review is one decision'` at `17ef052ecd264d9c99ca9b60b9fe5d4ccca6ec5d` | both English fixture rows absent from Sessions and timeout; fixed by stable row/scope testids | `default-port-preexisting-navigation-red.log` |
| Web unit regression | `npm test` | `43 passed`, `185 passed` | `web-unit.log` |
| Production build/type check | `npm run build` | exit `0`, Vite build completed | `web-build.log` |
| Focused formatting | `npx prettier --check e2e/agent-lifecycle-journey.spec.ts playwright.config.ts` | all matched files pass | `prettier-focused.log` |
| TypeScript no-excuse audit | skill checker via Node from `web/` | `No violations in 5 file(s)`, exit `0` | `no-excuse.log` |
| Diff hygiene and scoped stats | `git diff --check` plus scoped `git diff --stat` | `diff_check=pass` | `diff-loc.log` |

The lifecycle fixture proves only its frontend/mock browser request contract.
It does not claim production backend authorization, route enforcement, or
Human identity authority; those belong to Task 6.
