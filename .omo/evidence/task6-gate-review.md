# Task 6 final gate review

- recommendation: APPROVE
- exactCommit: `6aa861d9d6a3591fb619a287cd0079c509dca222`
- blockers: []
- originalIntent: Expand Mission write authority only through explicit, bounded, plan-first cohorts while proving independent plan and Inbox selection, idempotency, restart recovery, real execution/merge/Oracle side effects, rollback, and preserved Human authority.
- desiredOutcome: A four-cell authority matrix and real-route disposable-repository evidence prove plan-only, Inbox-only, both, and neither behavior without activating defaults/full traffic or deleting legacy writers; stale/duplicate and malformed requests fail safely; restart does not duplicate effects; parity is zero; rollback is legacy-first; dirty worktrees and Oracle failure cannot be reported as success; each expansion still requires explicit Human GO.
- userOutcomeReview: Confirmed at the exact commit. The focused route suite and a fresh real HTTP/disposable-git run reproduce the requested outcomes. No production activation, profile/default change, full-traffic selection, or hard deletion is present in the commit.

## Checked artifacts

- `.omo/plans/agent-lab-ux-flow-alignment-roadmap.md` Task 6 brief and acceptance criteria
- commit diff `6aa861d9^..6aa861d9`
- `app/server/routers/human_inbox.py`
- `docs/redesign-2026-07/mission-authority-cohort-matrix.md`
- `scripts/mission_authority_cohort_matrix.py`
- `scripts/mission_authority_real_route_harness.py`
- `tests/test_mission_authority_cohort_matrix.py`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-6.md`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-6/focused-tests.txt`
- `.omo/evidence/agent-lab-ux-flow-alignment-roadmap/task-6/manual-route.json`
- fresh disposable output root `/tmp/agent-lab-task6-gate.HHU3ak`

## Reproduced evidence

- Focused pytest: `127 passed in 11.41s`.
- Ruff: all checked changed Python files passed.
- Commit-scoped `git diff --check`: passed.
- Four-cell route probe:
  - plan-only: plan authority true, Inbox authority false, legacy Inbox written.
  - Inbox-only: plan authority false with `cohort_allowlist_empty`, Inbox authority true, no legacy Inbox write.
  - both: plan and Inbox authority true.
  - neither: both false, `cohort_allowlist_empty`, legacy Inbox written.
  - All four returned plan/create/resolve 200, duplicate 409, malformed 422.
- Fresh real-route harness: exit 0 and `pass=true`; PIDs `51259→51545`; restart read model 200; parity divergence 0; duplicate 409 with event delta 0; malformed 422; real merge/Oracle `[200,"pass"]`; reverify 200; dirty worktree 400; misleading HTTP success `[200,"fail","VERIFYING"]`; rollback returned 200 with `mirrored=false` and `reason=cohort_allowlist_empty`.
- Disposable repo HEAD `aac0d7a1026d9b5d8626ca11b9631d7023ff7c77` contains the merge commit and the journal contains one ordered merge/Oracle sequence. Port 18879 was no longer listening after completion and the server log contained no traceback/error.
- Profile registry is identical across the parent and reviewed commit for Mission flags; the diff contains no production default flip, full-traffic selector, hard-delete operation, or auto-approval path. Documentation and harness output explicitly retain Human GO.

## Direct programming and remove-ai-slops pass

- No deletion-only/removal-verification tests were introduced.
- The matrix-shape assertion is somewhat structural, but the parametrized route test and independent fresh route probe assert observable production-route outcomes, so it does not create criterion-level false confidence.
- No tautological expected value is derived from the route output under test.
- No implementation-mirroring mock substitutes for the real HTTP/disposable-git evidence.
- The harness is purpose-specific rather than an unnecessary production abstraction; it performs real route calls and real git side effects.
- Changed pure LOC counts are within the 250-line ceiling: `human_inbox.py` 210, cohort matrix 210, route harness 250, matrix test 68.
- The stale-answer boundary converts `MissionApplicationError` to the required HTTP 409; malformed Pydantic input remains 422.
- No maintenance/slop finding violates a stated Task 6 criterion.

## Evidence gaps and notes

- NOTE: No separate Task 6 code-review report or manual-QA matrix was found. The task evidence summary and raw command artifacts exist, and this direct gate pass reproduced every named criterion, so this is not a blocker under the review rules.
- NOTE: The checked evidence directory and plan are untracked in this worktree. The reviewed production/test/doc commit itself is cleanly identifiable at the exact SHA; the pre-existing dirty state was preserved and did not affect disposable-root verification.
- NOTE: The existing evidence's PID and git SHA were historical; this review did not trust them and generated fresh PIDs and a fresh disposable merge SHA.
- exactEvidenceGaps: separate code-review skill-coverage report absent; separate manual-QA matrix absent. Neither is a stated Task 6 acceptance artifact, and direct reproduction supplies the required coverage.
