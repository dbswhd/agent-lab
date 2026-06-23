# Architect Review — ultragoal G003: anti-drift B (unanimity red-team) + fresh-eyes critic seat + final verification

> NOTE: role-agent subagent dispatch down (executor/architect spawns failed sub-second repeatedly all session). Conducted INLINE by the ultragoal leader, source-verified. Disclosed.

## Verdict
- architectureStatus: CLEAR
- productStatus: CLEAR
- codeStatus: CLEAR
- recommendation: APPROVE
- blocking count: 0

## Scope reviewed
src/agent_lab/room_consensus_rounds.py (unanimity red-team trigger), src/agent_lab/plan_workflow.py (run_plan_peer_review_round fresh-eyes seat + PLAN_FRESH_EYES_GUIDANCE), turn_modes.antidrift_enabled (shared), tests/test_antidrift.py (AC8-AC10), tests/test_integration_registry.py (budget).

## Findings (against constraints)
1. B PANEL-ONLY BY CONSTRUCTION: the red-team trigger lives inside run_consensus_agent_rounds, which is only reached from room_turn_flow.py when consensus_mode is True (the `elif consensus_mode:` dispatch). solo (run_agent_rounds) never enters this function, so B is structurally unreachable in solo. OK (AC8).
2. B REUSES EXISTING MECHANISM, DOES NOT WEAKEN GATES: the change only widens the EXISTING forced-review trigger from `route.quality_gate` to `route.quality_gate OR (antidrift_enabled() and not route.quality_gate)` on the same `debate_conflicts == 0` (0-objection unanimity) condition. consensus_gate_met / objection detection untouched. The forced round demands a real CHALLENGE/AMEND (anti-formalism guidance already present). OK.
3. B RESPECTS CAPS: the trigger keeps the existing `len(active) >= 2 and calls < cap_calls` guard; forced_review_rounds stays exactly 1; the downstream consent loop still bounded by `parallel_round <= cap_rounds and calls < cap_calls`. No cap bypass. OK (AC9).
4. B SPINE UNTOUCHED: the path adds one advocate round and records quality["antidrift_redteam"]=True; it never transitions plan_workflow phase, never calls _mirror_verified_loop_status/approve_plan, never mutates verified_loop. OK (AC9, AC13 — verified_loop + plan_workflow regression suites green).
5. FRESH-EYES SEAT IN PEER_REVIEW ONLY: run_plan_peer_review_round adds exactly ONE extra cold-context critic round (empty message history + PLAN_FRESH_EYES_GUIDANCE, reusing the existing run_parallel_round primitive) when antidrift_enabled(); absent when off and absent in all other phases (this function is the PEER_REVIEW path). Additive to the returned replies. OK (AC10).
6. OFF-PARITY: both additions are guarded by antidrift_enabled(); with AGENT_LAB_ANTIDRIFT off the red-team trigger reduces to the original `route.quality_gate` condition and the fresh-eyes seat is skipped — byte-identical. Verified by the full suite staying green with the flag default-off and the consensus/plan_workflow regression tests unchanged. OK (AC6/AC14).
7. NO DYNAMIC POOL / NO LEARNED ORCHESTRATOR / NO NEW LAYER: additive hooks into existing consensus and peer-review paths only. OK (AC14).

## Code-side notes (non-blocking)
- AC8/AC9 are tested via a predicate mirror plus a source-string guard (test_redteam_predicate_matches_source) so the mirror cannot silently drift from the real condition; AC10 via mock-agent integration counting reviewer rounds + asserting the cold round uses empty history and cold guidance.
- Final verification: AC13 (spine/verified-loop regression) green; AC14 (both flags off) = full default-off suite green; AC15 full fast lane green + mypy baseline + ruff clean.

## Verification observed (leader-run, real)
- ruff check + format --check: clean.
- mypy ratchet: 243/243 (G003 delta 0; total run delta across all 3 stories = 0).
- make test-fast: 1529 passed, 1 skipped, 0 failed.
- focused: 88 passed (artifacts/g003-antidrift-qa.txt).
