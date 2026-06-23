# Plan Revision (stage 11) - Stage-Aware Selective Multi-Agent + Anti-Drift

> NOTE: planner/architect subagents are failing to spawn (transient infra; sub-second empty). This revision was authored INLINE by the ralplan leader, source-verified, addressing every stage-10 architect must-fix. Disclosed for audit.

## Chosen option: Opt-A (CORRECTED) - flag-gated phase->route table that sets the resolved ModeContract.consensus_mode at turn_modes.resolve_mode_contract; select_mode stays the telemetry surface only.

## Principles
1. Extend, do not add a layer: route through `turn_modes.resolve_mode_contract` + the existing `consensus_mode` gate at room_turn_flow.py:277; no parallel routing layer.
2. OFF-parity per flag: AGENT_LAB_STAGE_ROUTING and AGENT_LAB_ANTIDRIFT default off => resolve_mode_contract and the room turn path are byte-identical to today.
3. User override wins: phase-default applies ONLY when the user gave no explicit turn_profile (resolve_mode_contract already branches on turn_profile; divergence short-circuits first).
4. Mechanism-firing tests are the gate; telemetry (RoutingDecisionLog) is observation only; behavioral drift metrics are NOT a gate.
5. Approval spine untouched: plan_workflow._mirror_verified_loop_status / approve_plan unchanged; routing never starts execution.

## Decision Drivers
1. Correct lever: single-vs-panel is consensus_mode (room_turn_flow.py:277-296: run_consensus_agent_rounds vs run_agent_rounds), produced by resolve_mode_contract (turn_modes.py:99-159).
2. Coherent phase source available where the contract is resolved.
3. Minimal blast radius + provable OFF-parity.

## Lever relocation (resolves stage-10 BLOCKING)
- select_mode (mode_router.py:20) and record_mode_route stay CLASSIFY/OBSERVE -> repurposed as the RoutingDecisionLog telemetry emitter (phase, chosen consensus_mode, guard events). NOT the gate.
- The gate is `ModeContract.consensus_mode` from resolve_mode_contract. The phase->route table sets consensus_mode True for panel phases, False for solo phases.

## Phase source (resolves stage-10 HIGH)
- Single coherent source = the active mission/plan FSM phase already on run.json at the room layer: plan_workflow phase (INTAKE/CLARIFY/DRAFT/PEER_REVIEW/REFINE/HUMAN_PENDING) when plan_workflow active, else mission_loop phase (CLARIFY/DISCUSS/PLAN_GATE/EXECUTE_QUEUE/DRY_RUN/MERGE_REVIEW/VERIFY/REPAIR).
- The room caller (run_room/continue_room_round in room_turn_flow.py:134,536) already reads run_meta; it computes the active phase and passes a new optional `phase` kwarg into resolve_mode_contract.
- phase->route table (panel=consensus_mode True): DISCUSS, DRAFT, PEER_REVIEW, REFINE, divergence. solo=consensus_mode False: EXECUTE_QUEUE, DRY_RUN, MERGE_REVIEW, VERIFY, REPAIR, quick, scribe. CLARIFY -> DEFER to clarity engine (hybrid; do not set consensus_mode here).

## Step-by-step plan
1. runtime_flags.py: register AGENT_LAB_STAGE_ROUTING (default off) and AGENT_LAB_ANTIDRIFT (default off); expose via /api/health/flags. Additive; OFF-parity.
2. turn_modes.py: add a pure helper `phase_default_consensus(phase) -> bool|None` (None=defer, e.g. CLARIFY). Add optional `phase: str|None=None` kwarg to resolve_mode_contract; when AGENT_LAB_STAGE_ROUTING on AND no explicit user turn_profile (turn_profile falsy/default) AND phase_default_consensus(phase) is not None, set consensus_mode accordingly for the team/loop branches; otherwise unchanged. Divergence short-circuit and explicit-profile paths untouched. Flag off => identical contract.
3. room_turn_flow.py (run_room + continue_room_round): compute active phase from run_meta (plan_workflow phase else mission_loop phase) and pass `phase=` into the resolve_mode_contract call (or into the consensus_mode it forwards). No change to the 277/680 dispatch shape itself.
4. mode_router.py: extend record_mode_route into RoutingDecisionLog telemetry (phase, resolved consensus_mode, anti-drift guard events) - observational, gated by AGENT_LAB_STAGE_ROUTING for the new fields; never affects fan-out.
5. anti-drift A (re-injection): in the panel context build path (room_turn_flow / room_consensus_rounds context assembly), when AGENT_LAB_ANTIDRIFT on AND consensus_mode True, re-inject clarity.format_facts_block(run) + ledger digest every turn; solo path gets a light single inclusion. Reuse existing format_facts_block; additive.
6. anti-drift B (unanimity->red-team): inside run_consensus_agent_rounds / consensus_gate (only reached when consensus_mode True => panel-only/solo-never by construction), when AGENT_LAB_ANTIDRIFT on and a round is immediate 0-objection unanimity, force exactly one red-team/divergence round (respect existing loop caps; never bypass approval spine).
7. fresh-eyes cold critic: when the panel phase is PEER_REVIEW (audit), add one critic seat that receives goal+artifact-only cold context (no accumulated transcript), reusing the ralplan fresh-spawn pattern. Additive panel member; gated by AGENT_LAB_ANTIDRIFT.
8. Leave plan_workflow approval spine, consensus loop caps, verified_loop, divergence profile semantics unchanged.
9. Tests + verification (below).

## Acceptance Criteria (re-pointed + expanded; 15)
- AC1 phase->route: resolve_mode_contract(phase=DISCUSS/DRAFT/PEER_REVIEW/REFINE, no explicit profile, STAGE_ROUTING on) yields consensus_mode True; phase in EXECUTE_QUEUE/DRY_RUN/MERGE_REVIEW/VERIFY/REPAIR yields False. (asserts ModeContract.consensus_mode, NOT select_mode)
- AC2 divergence phase -> divergence contract unchanged (short-circuit intact).
- AC3 user-override: explicit turn_profile (e.g. quick/team/loop/divergence) overrides phase-default -> contract equals today's regardless of phase.
- AC4 phase-default applies ONLY when no explicit user turn_profile.
- AC5 OFF-parity routing: STAGE_ROUTING off => resolve_mode_contract returns byte-identical ModeContract for all (mode,synthesize,turn_profile,phase) combos vs today.
- AC6 OFF-parity anti-drift: ANTIDRIFT off => context build + consensus path byte-identical (no extra re-injection, no red-team, no critic seat).
- AC7 A re-injection: ANTIDRIFT on + consensus_mode True -> facts/ledger block present in panel context each turn; solo -> light single.
- AC8 B panel-only: unanimity in a consensus (panel) round forces one red-team round; B code path is unreachable when consensus_mode False (solo never triggers B).
- AC9 B respects caps + approval spine: forced red-team obeys loop caps; _mirror_verified_loop_status/approve_plan unchanged; no APPROVED/running side effect.
- AC10 fresh-eyes critic: PEER_REVIEW panel includes a cold-context critic seat (goal+artifact only); absent in non-audit panels and when ANTIDRIFT off.
- AC11 RoutingDecisionLog telemetry records phase/consensus_mode/guard events; is observational (no test gates on drift reduction; toggling telemetry never changes fan-out).
- AC12 CLARIFY defers to clarity engine (phase_default_consensus(CLARIFY) is None; no double-decision).
- AC13 approval spine regression: existing plan_workflow/verified-loop tests pass unchanged.
- AC14 dynamic pool deferred: no dynamic-pool/sovereignty code introduced.
- AC15 full fast lane green + mypy==baseline + ruff/format clean.

## Verification
Focused new tests: tests/test_stage_routing.py (AC1-AC5,AC12), tests/test_antidrift.py (AC6-AC10), tests/test_routing_telemetry.py (AC11); plus regression assertions for AC13/AC14. Then make test-fast (raise tests/test_integration_registry.py fast-bucket budget if needed), then ruff check + ruff format --check + mypy on changed files.

## Risks & mitigations
1. Lever entanglement: contract resolution is the single chokepoint; do not touch the 277/680 dispatch shape -> low blast radius.
2. Flag matrix (STAGE_ROUTING x ANTIDRIFT x explicit-profile x phase): enumerate in tests incl. both-off (parity), routing-on/antidrift-off, both-on.
3. B over-fire: gated to consensus path + unanimity + one round + caps.
4. Re-injection/critic cost: panel-stage only; reuse existing format_facts_block; one extra critic only in PEER_REVIEW.
5. CLARIFY double-decision: phase_default returns None for CLARIFY -> clarity engine owns it.
6. Approval-spine bypass: B/critic never call approve_plan/_mirror_verified_loop_status; AC9/AC13 assert.

## RALPLAN-DR
- Principles: extend-not-layer, per-flag OFF-parity, user-override-wins, mechanism-tests-gate, spine-untouched.
- Drivers: correct lever (consensus_mode/resolve_mode_contract), coherent phase source, provable parity.
- Options: Opt-A corrected (chosen) | Opt-B thin policy module (rejected: still a new indirection over the same lever) | Opt-C execute-only (rejected: fails approved panel/audit scope).
