# Architect Re-Review (stage 12) - Revision verification

> NOTE: architect subagent spawn failing repeatedly (transient infra). Conducted INLINE by ralplan leader, source-verified. Disclosed.

## Verdict
- architectureStatus: CLEAR
- productStatus: CLEAR
- codeStatus: CLEAR
- recommendation: APPROVE
- blocking count: 0

## Prior BLOCK closure (verified)
The stage-10 BLOCKING lever mis-location is CLOSED. The revision relocates the phase->route table to set `ModeContract.consensus_mode` via `turn_modes.resolve_mode_contract(phase=...)`, which is the real single-vs-panel gate consumed at room_turn_flow.py:277 (run_consensus_agent_rounds vs run_agent_rounds). select_mode/record_mode_route are correctly demoted to the RoutingDecisionLog telemetry surface (observational, not the gate).

## Confirmed (against source)
1. Correct lever: consensus_mode at room_turn_flow.py:277-296 is sourced from resolve_mode_contract (turn_modes.py:99-159). Revision step 2/3 targets exactly this. OK.
2. User-override-wins is structural: resolve_mode_contract branches on turn_profile and `_is_divergence` short-circuits first (turn_modes.py:109,121); revision applies phase-default ONLY when no explicit profile (AC3/AC4). OK.
3. B panel-only/solo-never is structural: run_consensus_agent_rounds only runs when consensus_mode True; hooking B inside that path makes solo unreachable by construction (AC8). OK.
4. A reuses clarity.format_facts_block + ledger in panel context build; additive (AC7). OK.
5. CLARIFY defers to the shipped clarity engine via phase_default_consensus(CLARIFY)=None (AC12) - no double-decision. OK.
6. Approval spine untouched: B/critic never call approve_plan/_mirror_verified_loop_status (AC9/AC13). OK.
7. Per-flag OFF-parity asserted (AC5 routing, AC6 anti-drift) as ModeContract equality + byte-stable path. OK.

## WATCH (non-blocking, execution-time)
- The room-layer 'active phase' computation (plan_workflow phase when active else mission_loop phase) must be pinned precisely during implementation so the phase->route table reads one unambiguous value; AC1/AC4/AC12 constrain it but the executor should add a focused unit test for the phase-resolution helper itself.
- agent_rounds/parallel_rounds interaction with consensus_mode (room_turn_flow.py:276 parallel_rounds path) should be checked so a panel phase that sets consensus_mode True does not double-count rounds; covered by AC1 + AC15 fast lane but worth an explicit assertion.

## AC verdict
AC1-AC15 are testable and sufficient; the phase->mode AC is correctly re-pointed to ModeContract.consensus_mode. No missing AC. Add the two WATCH unit checks during execution (phase-resolution helper; rounds non-double-count).
