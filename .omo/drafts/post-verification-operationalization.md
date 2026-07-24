---
slug: post-verification-operationalization
status: awaiting-approval
intent: clear
review_required: false
pending-action: write .omo/plans/post-verification-operationalization.md
approach: Collect a bounded live supervisor cohort without changing defaults, validate fresh success and FAIL→repair evidence, obtain explicit Human GO, then make only a reversible cohort-scoped default change with rollback and observation.
---

# Draft: post-verification-operationalization

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
| live-cohort | Real supervisor sessions exercise topic → Room → Decision Queue → plan/worktree/diff → Oracle, including one repair path. | active | `docs/DOGFOOD-READINESS-STATUS.md` |
| readiness-packet | Fresh packet distinguishes live evidence from mock/browser evidence and stays fail-closed. | active | `docs/evidence/dogfood-readiness/manifest.json` |
| human-go | A human decides whether the evidence permits any default routing/authority change. | active | `docs/DOGFOOD-READINESS-STATUS.md` |
| staged-rollout | Only after GO, make a reversible bounded-cohort default change and observe/rollback. | active | `docs/TURN-CONTRACT.md` |
| separate-backlog | F7, N4-D3, and HS-M5 remain independently scheduled work; they are not evidence for this rollout. | deferred | `docs/NOW.md` |

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->
| rollout scope | Keep defaults unchanged through evidence collection; first change is cohort-scoped, never full traffic. | Current packet is OPEN with `live n=0`; documentation requires explicit Human GO. | yes |
| success evidence | Require both a success and a bounded FAIL→repair/re-discuss run, each with retained Oracle evidence. | Browser audit already proves the contract; live operational evidence is the missing category. | yes |
| operational artifacts | Store live reports locally/ignored and commit only redacted summaries/manifest changes when justified. | Existing reproduction guidance separates live reports from committed mock references. | yes |

## Findings (cited - path:lines)
- `docs/DOGFOOD-READINESS-STATUS.md:3,10-19` says the current state is `OPEN`; browser contract is PASS (`n=4`), live is `OPEN` (`n=0`), and default authorization is false pending explicit Human GO.
- `.claude/worktrees/codex-ux-flow-final4/.omo/evidence/wave-b-m6-retire/task-5/final5-qa-retry/runtime-audit/manual-qa.md` confirms the runtime safety contract at `611a57da35bf1f55214b43bac19cce33b0acd9f5`: Oracle-gated completion, fail-closed readiness, and stale-action rejection all passed.
- `docs/NOW.md:88-103` identifies other dogfood tracks still open (F7, N4-D3, HS-M5); they must not be bundled into this rollout.

## Decisions (with rationale)
- Treat the present final verification as implementation/browser-contract completion, not a live rollout approval.
- Order work as live evidence → readiness recomputation → Human GO → bounded rollout → observation/rollback decision.

## Scope IN
- Live supervisor cohort using the existing topic-only Composer and Human Inbox gates.
- Fresh success and intentional Oracle FAIL→repair/re-discuss evidence.
- Regenerated readiness packet, explicit Human decision record, and reversible cohort-only rollout if approved.

## Scope OUT (Must NOT have)
- No default routing/authority flip before live evidence and explicit Human GO.
- No full-traffic cutover, new product surface, or unrelated F7/N4-D3/HS-M5 implementation in this plan.
- No claim that mock/browser evidence constitutes live operational readiness.

## Open questions
- What minimum live cohort should authorize the Human GO review? Recommended: three successful full journeys plus one bounded FAIL→repair/re-discuss journey; this is an operational safety threshold and should be owner-approved.
- Should the first authorized change be routing, authority, or both? Recommended: one reversible cohort-scoped flag at a time, routing first; this limits blast radius and preserves a clear rollback signal.

## Approval gate
status: awaiting-approval
<!-- When exploration is exhausted and unknowns are answered, set status: awaiting-approval. -->
<!-- That durable record is the loop guard: on a later turn read it and resume at the gate instead of re-running exploration. -->
Approval authorizes writing the detailed execution plan only; it does not authorize live execution or a default flip.
