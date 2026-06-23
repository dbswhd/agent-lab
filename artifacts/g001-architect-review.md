# Architect Review — ultragoal G001: stage-aware routing core + RoutingDecisionLog telemetry

> NOTE: role-agent subagent dispatch was down (architect spawn failed sub-second ×4 this session). This review was conducted INLINE by the ultragoal leader, source-verified against the files below. Disclosed for audit.

## Verdict
- architectureStatus: CLEAR
- productStatus: CLEAR
- codeStatus: CLEAR
- recommendation: APPROVE
- blocking count: 0

## Scope reviewed
src/agent_lab/turn_modes.py, src/agent_lab/mode_router.py, src/agent_lab/room_turn_flow.py, src/agent_lab/runtime_flags.py, src/agent_lab/clarity.py (1-line annotation), .env.example, tests/test_stage_routing.py, tests/test_routing_telemetry.py, tests/test_stage_routing_redteam.py, tests/test_integration_registry.py.

## Findings (against constraints)
1. CORRECT LEVER (verified vs source): the single-vs-panel fan-out is decided by `consensus_mode` at room_turn_flow.py (`elif consensus_mode:` -> run_consensus_agent_rounds [PANEL] else run_agent_rounds [single]). `_resolve_stage_routing(...)` overrides `consensus_mode` in BOTH continue_room_round and run_room immediately BEFORE `_set_active_turn_flags` (which writes run_meta._active_consensus), so downstream task-assignment, parallel rounds, and dispatch all read the resolved value consistently. `turn_modes.resolve_mode_contract` is dead code (zero callers) and was correctly left untouched; the planned dead-function `phase` kwarg was dropped to avoid needless surface. OK.
2. OFF-PARITY (per-flag): `_resolve_stage_routing` returns the input consensus_mode unchanged and writes nothing when AGENT_LAB_STAGE_ROUTING is off; `stage_route_consensus(..., stage_routing=False)` is a proven identity on consensus_mode for every phase/profile. Verified empirically by revert-test (mypy ratchet identical 244 with and without the room blocks) and by the full fast lane staying byte-stable (1490 passed/1 skipped). OK.
3. USER-OVERRIDE-WINS: `stage_route_consensus` applies the phase default only when `turn_profile` is empty/None (whitespace-only is NOT explicit); any explicit profile (loop/team/quick/divergence/specialist/verified) keeps the caller's contract. divergence dedicated contract path untouched. OK (AC2/AC3/AC4 + red-team).
4. TELEMETRY OBSERVATIONAL: `record_routing_decision` writes only run.json mission_loop.stage_route, is a no-op without a folder, never injects dispatch/fan-out keys (_active_consensus/agents), and is only called inside the flag-on guard (never written when off). OK (AC11 + red-team no-fan-out-injection test).
5. APPROVAL SPINE UNTOUCHED: no changes to plan_workflow._mirror_verified_loop_status or approve_plan or verified_loop; not in the changeset. No dynamic model pool; no learned orchestrator; no new parallel routing layer (extends existing turn-mode/room path). OK.
6. CLARIFY DEFERS: phase_default_consensus returns None for CLARIFY/INTAKE/MISSION_DEFINE/unknown so stage routing never overrides the clarity engine. OK (AC12).
7. clarity.py:442 annotation: pure `interview: dict[str, Any]` type annotation that clears a pre-existing var-annotated mypy error (uncommitted CLARIFY-era debt) blocking the ratchet; zero behavior change. Acceptable as an orthogonal fix-at-source; restores ratchet to committed baseline 243/243.

## Code-side notes (non-blocking)
- Duplication between the two room call sites was resolved by extracting the module helper `_resolve_stage_routing` (DRY). 
- Test coverage is mechanism-firing and adversarial: AC1-AC5/AC11/AC12 + phase-resolution precedence + decision-log non-double-count + 42 red-team cases (casing/whitespace/garbage run dicts/falsy folders/flag spellings/total OFF-parity identity).

## Verification observed (leader-run, real)
- ruff check + ruff format --check: clean (all changed files).
- mypy ratchet: 243/243 (excluding room.py) == committed baseline; G001 delta proven 0 via revert-test.
- make test-fast: 1490 passed, 1 skipped, 0 failed.
- focused + red-team: 85 passed (artifacts/g001-stage-routing-qa.txt).
