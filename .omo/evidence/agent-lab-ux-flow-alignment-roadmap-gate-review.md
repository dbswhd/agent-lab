# F1 final gate review

## recommendation

APPROVE

Exact reviewed SHA: `01431f27a875ff0582a5d9e3f6905432eb0627c4`

## originalIntent

Ship the F1 roadmap as a Human-gated user journey from topic submission through
risk/intent-aware Room work, one Decision Queue action at a time, explicit plan
approval/revision, isolated dry-run and diff review, explicit merge, bounded
Oracle repair/re-discuss, and PASS-only completion. Follow it with shadow-only
TurnContract evidence, bounded Mission authority, and truthful dogfood readiness.

## desiredOutcome

All seven roadmap tasks are represented without restoring a Work navigation tab
or Plan toggle, without automatic approval/merge/repair, and without changing
global routing or authority defaults. Roles/adaptive promotion and authority
expansion continue to require recorded Human GO. Live readiness remains OPEN
until real evidence satisfies the declared gates.

## userOutcomeReview

The reviewed artifact represents the complete journey and preserves the stated
authority boundaries. The Decision Queue projects one active Inbox item and a
queued count. The lifecycle E2E covers risk/intent, plan revision and approval,
dry-run, durable unmerged diff, explicit merge, Oracle FAIL repair/re-discuss,
and PASS-only closure. TurnContract remains `shadow` by default and promotion
reports only `HUMAN_GO_REQUIRED`. Mission authority uses non-empty session
allowlists and leaves non-cohort/default behavior unchanged. The dogfood packet
fails closed on empty or browser-only live proof and reports readiness `OPEN`.

Task 7 is therefore **OPEN live readiness**, not a PASS claim. This is the
truthful intended outcome and not a blocker.

## coverage matrix

| Task | Result | Direct evidence |
| --- | --- | --- |
| 1 — topic to risk/intent Room | covered | `web/e2e/agent-lifecycle-journey.spec.ts:1160`, fixture projection at lines 354-355 |
| 2 — one Decision Queue gate | covered | `web/src/components/HumanInboxPanel.tsx:75`, `web/src/components/HumanInboxPanel.tsx:902`, `web/src/components/HumanInboxPanel.test.ts` |
| 3 — plan approve/revise, dry-run/diff, explicit merge | covered | `web/e2e/agent-lifecycle-journey.spec.ts:1160`, `:1254`, `:1349` |
| 4 — Oracle FAIL repair/re-discuss and PASS-only completion | covered | `web/e2e/agent-lifecycle-journey.spec.ts:1349`, `:1424`, `:1575` |
| 5 — safe TurnContract shadow gates | covered | `src/agent_lab/room/turn_contract_promotion.py`, `src/agent_lab/room/turn_contract_evidence.py`, `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-5.md` |
| 6 — bounded Mission authority | covered | `scripts/mission_authority_cohort_matrix.py`, `scripts/mission_authority_real_route_harness.py`, `docs/redesign-2026-07/mission-authority-cohort-matrix.md` |
| 7 — truthful dogfood readiness | covered, OPEN | `scripts/dogfood_readiness_manifest.py`, `scripts/dogfood_readiness_packet.py`, `docs/DOGFOOD-READINESS-PACKET.md`, `docs/NOW.md:37` |

## blockers

None.

## checked artifact paths

- Branch diff from merge-base with `main` through exact reviewed SHA
- `.agent-lab/PROJECT.md`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-5.md`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task5/*`
- `docs/FLOW.md`
- `docs/USER-GUIDE.md`
- `docs/TURN-CONTRACT.md`
- `docs/DOGFOOD-READINESS-PACKET.md`
- `docs/redesign-2026-07/mission-authority-cohort-matrix.md`
- `docs/NOW.md`
- all 49 changed-file paths from the branch diff

## reproduced checks

- `PYTHONPATH=src .../pytest tests/test_turn_contract_promotion.py tests/test_outcome_harvester_execute.py tests/test_mission_authority_cohort_matrix.py tests/test_dogfood_readiness_report.py -q`
  — `31 passed in 6.98s`
- Ruff over all changed Python production/test paths — `All checks passed!`
- `git diff --check $(git merge-base main HEAD)..HEAD` — clean
- Worktree HEAD and requested SHA matched exactly before report creation.

## direct remove-ai-slops / programming pass

No criterion-blocking slop, scope drift, unsafe default flip, broad authority
expansion, or false-confidence readiness claim was found. The Python additions
use typed boundary models and adversarial fail-closed tests. Tests exercise
stale/malformed evidence, empty live samples, browser-only proof, non-cohort
behavior, and Human checkpoints rather than only happy paths.

`web/e2e/agent-lifecycle-journey.spec.ts` is a large, self-contained 1,643-line
fixture and is a maintenance NOTE under the oversized-module/slop criteria. It
does not violate a stated F1 success criterion and therefore is not a blocker.
No task-specific code-review report explicitly demonstrating both skill
perspectives was present; direct inspection and reproduced checks supplied the
required coverage, so this is also a NOTE rather than a blocker.

## exact evidence gaps

- Frontend Vitest/Playwright could not be reproduced in this worktree because
  dependencies are not installed/resolvable there (`vitest: command not found`;
  borrowing the parent binary failed to resolve `vite`). The committed test
  sources were inspected directly. This is not tied to a stated criterion that
  requires a fresh local frontend run, so it does not block approval.
- There is intentionally no live credentialed Task 7 evidence packet. The
  production validator rejects a live PASS without a positive sample and a
  non-mock Oracle verdict; documentation and current status remain OPEN.
