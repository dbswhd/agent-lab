# Architect Review (stage 10) - Stage-Aware Selective Multi-Agent + Anti-Drift

> NOTE: Architect subagent spawn failed twice (sub-second, empty output = transient infra). This review was conducted INLINE by the ralplan leader, source-verified against real files. Disclosed for audit honesty.

## Verdict
- architectureStatus: BLOCK
- productStatus: WATCH
- codeStatus: WATCH
- recommendation: REQUEST CHANGES
- blocking count: 1 (+ 1 HIGH)

## Steelman antithesis (confirmed against source)
The Planner Opt-A puts the lever at `mode_router.select_mode` extended with a phase->route table. But `select_mode` (src/agent_lab/mode_router.py:20-32) is PURE CLASSIFY/OBSERVE: it returns CLARIFY/CONSENSUS/EXECUTE and `record_mode_route` only persists an observable route. It does NOT gate single-vs-panel fan-out. The REAL single-vs-panel decision is `consensus_mode` consumed at src/agent_lab/room_turn_flow.py:277-296 (`elif consensus_mode:` -> room.run_consensus_agent_rounds [PANEL] else room.run_agent_rounds [single] with parallel_rounds), and `consensus_mode`/`agents`/`agent_rounds` are produced by `turn_modes.resolve_mode_contract` -> `ModeContract` (turn_modes.py:99-159). Extending select_mode therefore does NOT change fan-out -> the plan's core mechanism is mis-located.

## Findings
1. BLOCKING - lever mis-location. Relocate phase-awareness to influence the resolved `ModeContract.consensus_mode` (and agents/agent_rounds) at the point feeding run_room/continue_room_round, i.e. extend/wrap `turn_modes.resolve_mode_contract` (turn_modes.py:99) and/or the caller that passes `consensus_mode` into room_turn_flow (room_turn_flow.py:134,536). The phase->route table must set consensus_mode True for panel phases (DISCUSS/DRAFT/PEER_REVIEW/REFINE/divergence) and False for solo phases (EXECUTE/merge.verify/quick/scribe). select_mode/record_mode_route may remain as the OBSERVABILITY/telemetry surface (RoutingDecisionLog), which is actually a clean fit - but it is not the gate.
2. HIGH - phase vocabulary incoherence. Three phase namespaces exist: mode_router (EXECUTE_QUEUE/DRY_RUN/MERGE_REVIEW/VERIFY/REPAIR/DISCUSS/PLAN_GATE), plan_workflow (INTAKE/CLARIFY/DRAFT/PEER_REVIEW/REFINE/HUMAN_PENDING/APPROVED), turn_modes (user_mode quick/team/loop + profiles divergence/specialist/verified/free). The plan must pick ONE coherent phase source available at the resolve point and map every spec phase to a real signal, stating which FSM provides each. Today resolve_mode_contract keys off `turn_profile` + mode + synthesize, NOT mission/plan FSM phase - so 'phase-aware' must define how the FSM phase reaches resolve_mode_contract.
3. MEDIUM (favorable, make explicit). 'User override always wins' is naturally satisfied: resolve_mode_contract already branches on turn_profile and `_is_divergence` short-circuits first (turn_modes.py:109). The phase-default must apply ONLY when the user gave no explicit profile; confirm and test. 'B (unanimity->red-team) panel-only / solo-never' is naturally satisfied because run_consensus_agent_rounds (consensus_gate/room_consensus_rounds) only runs when consensus_mode True; hook B INSIDE that consensus path so solo can never trigger it.
4. MEDIUM - OFF-parity per flag. With AGENT_LAB_STAGE_ROUTING off, resolve_mode_contract must return today's ModeContract byte-identically (quick=1 agent, team=consensus_mode False, loop=consensus_mode or route_auto). Add a per-flag OFF-parity test asserting contract equality. Same for the anti-drift flag(s).
5. LOW - CLARIFY reconciliation. CLARIFY single-vs-panel is already governed by the shipped clarity engine (clarity backs server clarifier). The phase table must DEFER CLARIFY to the clarity engine (hybrid), not double-decide.

## AC verdict (AC1..AC11)
Mostly testable, but: the phase->mode AC must assert the resolved ModeContract.consensus_mode/agents, NOT select_mode output (re-point after relocation). ADD: (a) resolve_mode_contract OFF-parity equality test per flag; (b) 'phase default applies only when no explicit user turn_profile' test; (c) B-hooks-inside-consensus-path (solo never reaches B) test; (d) CLARIFY-defers-to-clarity-engine test. With these, AC set is sufficient.

## Synthesis
The direction and constraints are sound; only the implementation locus is wrong. Re-aim the same flag-gated phase table at resolve_mode_contract / consensus_mode (keep select_mode as the telemetry surface), and several spec invariants (user-override, B-panel-only) fall out for free from existing structure. With the lever relocated and the 4 ACs added, this is APPROVE-able.
