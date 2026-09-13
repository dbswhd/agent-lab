# F4 exact-SHA gate review

- recommendation: REJECT
- reviewed SHA: `25eeead92ee85c8853368c670d2f72136e8ea703`
- repository: `/Users/yoonjong/Projects/agent-lab/.claude/worktrees/codex-ux-flow-final3`

## Original intent

Verify that every current, non-archive documentation surface consistently describes:

1. the Composer as topic-only, with no visible Plan toggle;
2. no visible Work navigation tab;
3. Wave B browser-contract acceptance as green while live/operational readiness remains `OPEN`;
4. `default_change_authorized=false`; and
5. an explicit Human GO as mandatory before any default routing/authority change, full-traffic cutover, or equivalent operational-completion claim.

## Desired outcome

At the exact reviewed SHA, a reader following any current documentation entry point should receive the same current UI and operational-readiness contract, without a current/shipped document reintroducing the removed Work tab or Plan control.

## User outcome review

The readiness and authority-boundary portion passes. `docs/DOGFOOD-READINESS-STATUS.md` is explicit that browser acceptance is green from four mocked-route tests, live readiness is `OPEN` with `n=0`, `default_change_authorized=false`, and explicit Human GO is required after live gates pass. The same boundary is repeated consistently in `.agent-lab/PROJECT.md`, `docs/FLOW.md`, `docs/NOW.md`, `docs/USER-GUIDE.md`, `docs/EXTERNAL-REFS-TRACEABILITY.md`, and the current redesign documents.

The all-current-docs UI consistency criterion fails. Although `docs/developer-agent-console.md` now correctly says the Composer is topic-only, Plan controls are hidden, and Work/Inbox/Tasks tabs are removed, current non-archive documents still direct readers to or describe a visible Work tab:

- `docs/README.md:46`, `:51`, and `:148` label current UI entry points as “Work 탭” / “Work tab Pipeline stepper,” including a claim that `developer-agent-console.md` is the current console reference with a Work-tab stepper.
- `docs/MISSION-LOOP-C-OMO.md:350` and `:383-393` is marked “Shipped” and describes Inspector + Work tab and shipped Work-tab alignment. It also links `docs/WORK-TAB-IA.md`, which does not exist at the reviewed SHA; the historical document is under `docs/archive/legacy/WORK-TAB-IA.md`.
- `docs/UI-IA-ROADMAP.md:75` and `:166-178` is explicitly a target roadmap, so it is not treated as proof of current shipped UI by itself. It nevertheless contributes navigation ambiguity because `docs/README.md` indexes it alongside the current console material.

This contradicts the current contract in `docs/FLOW.md:63-65`, `docs/USER-GUIDE.md:203`, and `docs/developer-agent-console.md:27-36`.

## Blockers

1. violatedCriterion: `F4-DOC-UI-CONSISTENCY`
   - observation: Current, non-archive documentation still asserts or indexes a visible/shipped Work tab, contradicting the topic-only Composer plus removed Work-navigation contract.
   - evidencePointer: `docs/README.md:46`, `docs/README.md:51`, `docs/README.md:148`, `docs/MISSION-LOOP-C-OMO.md:350`, `docs/MISSION-LOOP-C-OMO.md:383-393`; contradictory current contract at `docs/FLOW.md:63-65`, `docs/USER-GUIDE.md:203`, and `docs/developer-agent-console.md:27-36`.

## Checked artifacts

- Exact commit and one-file diff: `git show 25eeead92ee85c8853368c670d2f72136e8ea703`
- `.agent-lab/PROJECT.md`
- `docs/developer-agent-console.md`
- `docs/FLOW.md`
- `docs/USER-GUIDE.md`
- `docs/README.md`
- `docs/MISSION-LOOP-C-OMO.md`
- `docs/UI-IA-ROADMAP.md`
- `docs/TURN-MODES.md`
- `docs/TURN-POLICY.md`
- `docs/05-room-agent-roles.md`
- `docs/DOGFOOD-READINESS-STATUS.md`
- `docs/evidence/dogfood-readiness/manifest.json`
- `docs/evidence/dogfood-readiness/browser-contract.txt`
- `docs/NOW.md`
- `docs/EXTERNAL-REFS-TRACEABILITY.md`
- `docs/redesign-2026-07/11-ui-ux-surface-map.md`
- `docs/redesign-2026-07/13-document-governance-and-execution-plan.md`
- `docs/redesign-2026-07/mission-authority-cohort-matrix.md`

## Direct remove-ai-slops / programming pass

- The reviewed commit changes one prose line only. No production extraction, parsing, normalization, test addition, deletion-only test, tautological assertion, prompt/prose pin, or implementation-mirroring test was introduced.
- The edited line is concise and contract-bearing; it is not needless abstraction or defensive prose.
- The blocker is documentation scope drift/stale current references, not code style or architecture taste.

## Evidence gaps

- `omo ulw-loop status --json` returned `ULW_LOOP_PLAN_MISSING`, so the mandated fallback report path is used.
- No executor report, code-review report, manual-QA matrix, or notepad path was supplied for this bounded exact-SHA audit. These are not additional blockers because the direct artifact inspection proves the stated UI-consistency criterion failure.
- No test execution was needed to establish the documentation contradiction. The browser evidence was inspected as recorded evidence and was not promoted to live-readiness proof.
