# Final Plan (pending approval): Stage-Aware Selective Multi-Agent + Anti-Drift

> Consensus: Planner (stage-09) -> Architect BLOCK (stage-10) -> Revision (stage-11) -> Architect APPROVE/CLEAR (stage-12) -> Critic OKAY (stage-13). Architect/Critic of stages 10/12/13 were leader-run inline because role-agent subagent spawn was failing (transient infra); all source-verified. Run 2026-06-19-1737-8485.
> Source: approved deep-interview spec .gjc/specs/deep-interview-stage-aware-selective-multiagent.md (ambiguity 16.5%).

## ADR
- Decision: Convert agent-lab multi-agent from always-N-concurrent to STAGE-AWARE SELECTIVE by making the existing turn-mode contract phase-aware. A flag-gated phase->route table sets the resolved `ModeContract.consensus_mode` in `turn_modes.resolve_mode_contract` (the real single-vs-panel lever consumed at room_turn_flow.py:277). Panel phases (DISCUSS/DRAFT/PEER_REVIEW/REFINE/divergence) -> consensus_mode True; solo phases (EXECUTE_QUEUE/DRY_RUN/MERGE_REVIEW/VERIFY/REPAIR/quick/scribe) -> False; CLARIFY defers to the shipped clarity engine. Anti-drift (flag-gated): A) re-inject established_facts/ledger in panel context, B) unanimity->one red-team round inside the consensus path (panel-only by construction), and a fresh-eyes cold-context critic seat in the PEER_REVIEW panel. select_mode/record_mode_route become the RoutingDecisionLog telemetry surface (observational).
- Drivers: correct lever (consensus_mode/resolve_mode_contract, not classify-only select_mode); coherent phase source at the room layer; provable per-flag OFF-parity.
- Alternatives considered: Opt-B thin policy module (rejected - new indirection over the same lever); Opt-C execute-only-solo (rejected - fails approved panel/audit scope); original Opt-A-at-select_mode (rejected by architect - select_mode does not gate fan-out).
- Why chosen: extends the one real chokepoint with minimal blast radius; user-override-wins and B-solo-never fall out of existing structure; honors spec constraints (extend/no-layer, additive, OFF-parity, spine untouched).
- Consequences: two new default-off flags (AGENT_LAB_STAGE_ROUTING, AGENT_LAB_ANTIDRIFT); resolve_mode_contract gains an optional phase kwarg + phase_default helper; room layer computes active phase; panel context gains re-injection; consensus path gains unanimity red-team + audit critic seat. All additive, flags-off = byte-identical.
- Follow-ups (deferred): dynamic model pool + sovereignty (Round 0 deferral); re-injection cadence tuning via telemetry; learned routing is explicitly out of scope.

## Flags
- AGENT_LAB_STAGE_ROUTING (default off): phase-aware consensus_mode default.
- AGENT_LAB_ANTIDRIFT (default off): A re-injection + B unanimity red-team + fresh-eyes audit critic seat.
User explicit turn_profile always overrides the phase default (resolve_mode_contract branches on turn_profile; divergence short-circuits first).

## Plan (sequenced)
1. runtime_flags.py: register both flags default-off + /api/health/flags. OFF-parity.
2. turn_modes.py: add pure `phase_default_consensus(phase)->bool|None` (None=defer, e.g. CLARIFY); add optional `phase` kwarg to resolve_mode_contract; apply phase default to consensus_mode ONLY when STAGE_ROUTING on AND no explicit user turn_profile AND default not None; divergence/explicit paths unchanged; flag off => identical contract.
3. room_turn_flow.py (run_room + continue_room_round): compute active phase (plan_workflow phase when active else mission_loop phase) and pass phase= into the contract resolution / consensus_mode it forwards. Dispatch shape at :277/:680 unchanged.
4. mode_router.py: extend record_mode_route into RoutingDecisionLog telemetry (phase, resolved consensus_mode, anti-drift guard events); observational; never affects fan-out.
5. anti-drift A: panel context build (room_turn_flow / room_consensus_rounds) re-injects clarity.format_facts_block(run)+ledger each panel turn when ANTIDRIFT on; solo light single.
6. anti-drift B: inside run_consensus_agent_rounds/consensus_gate (reached only when consensus_mode True): immediate 0-objection unanimity forces one red-team/divergence round, respecting loop caps; never touches approval spine.
7. fresh-eyes critic: PEER_REVIEW panel adds one cold-context (goal+artifact-only) critic seat reusing the ralplan fresh-spawn pattern; ANTIDRIFT-gated.
8. Leave approval spine (plan_workflow._mirror_verified_loop_status, approve_plan), consensus loop caps, verified_loop, divergence semantics unchanged.

## Acceptance Criteria (15)
AC1 phase->route sets ModeContract.consensus_mode (panel True / solo False), asserted on the contract not select_mode. AC2 divergence contract unchanged. AC3 explicit profile overrides phase default. AC4 phase default applies only when no explicit profile. AC5 STAGE_ROUTING-off contract byte-identical (per-flag OFF-parity). AC6 ANTIDRIFT-off path byte-identical. AC7 A re-injection in panel (facts/ledger block each turn), solo light. AC8 B fires on unanimity in consensus path; unreachable in solo. AC9 B respects caps; spine unchanged (no APPROVED/running). AC10 PEER_REVIEW panel has cold-context critic seat; absent elsewhere/off. AC11 RoutingDecisionLog observational (no fan-out effect; no write when STAGE_ROUTING off). AC12 CLARIFY defers to clarity engine. AC13 approval-spine/verified-loop regression green. AC14 no dynamic-pool code. AC15 full fast lane green + mypy==baseline + ruff/format clean. (+exec WATCH: phase-resolution helper unit test; consensus_mode/parallel_rounds non-double-count.)

## Verification
Focused: tests/test_stage_routing.py, tests/test_antidrift.py, tests/test_routing_telemetry.py + spine regression. Then make test-fast (raise fast-bucket budget if needed), ruff check + ruff format --check, mypy on changed files.

## Risks & mitigations
1. Lever entanglement -> single chokepoint (resolve_mode_contract), dispatch shape untouched. 2. Flag matrix -> enumerated tests incl both-off parity. 3. B over-fire -> consensus-path + unanimity + one round + caps. 4. Cost -> panel-stage only, reuse format_facts_block, one extra critic only in PEER_REVIEW. 5. CLARIFY double-decision -> defer (None). 6. Spine bypass -> AC9/AC13.

## Status: PENDING APPROVAL
No product code mutated. Execution (default /skill:ultragoal) is a separate approval-gated step.
