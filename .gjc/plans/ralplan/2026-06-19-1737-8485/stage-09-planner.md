# Planner Draft: Stage-aware selective multi-agent routing

## Summary
Refine the approved deep-interview spec into an execution-ready, additive implementation plan for agent-lab. The selected design is Opt-A: extend `src/agent_lab/mode_router.py::select_mode` with a flag-gated phase-aware routing decision table, then consume the resulting decision at the existing room turn dispatch sites in `room_turn_flow.py` to choose solo versus panel without creating a parallel routing layer. Anti-drift A and B are added as independent default-off flags and tests gate mechanism firing, not behavioral drift metrics.

## Principles
1. Extend, do not add a routing layer: `mode_router.select_mode` remains the source of routing classification and gains phase-aware metadata/helpers under flag.
2. OFF-parity by construction: all new behavior is additive and gated; flags off preserve current return values, agent fanout, context payloads, consensus behavior, and approval flow.
3. User override wins: explicit turn-profile choices such as `quick`, `team`, `loop`, `divergence`, `verified`, or `specialist` override stage-routing defaults.
4. Mechanism-firing tests are the gate: deterministic unit tests prove phase mapping, override precedence, OFF-parity, re-injection, red-team firing, cold critic participation, and untouched approval spine.
5. Approval spine untouched: no changes to `_mirror_verified_loop_status`, `approve_plan`, execute approval gates, or verified-loop approval semantics.

## Decision Drivers
1. Preserve brownfield semantics while reducing always-N-concurrent fanout in convergence and execution phases.
2. Keep routing deterministic, observable, and testable without a learned orchestrator or dynamic model pool.
3. Avoid drift in long/panel stages with low-risk structural guards that are cheap to test and easy to disable independently.

## Viable Options
### Opt-A: extend `mode_router.select_mode` with a phase to route table, consumed by room dispatch behind `AGENT_LAB_STAGE_ROUTING` (selected)
Pros:
- Honors the spec: extension of the existing router, no new parallel routing layer.
- Centralizes phase mapping near current `_EXECUTE_PHASES` and `_CONSENSUS_PHASES`.
- Lets `record_mode_route` and a new RoutingDecisionLog observe the same decision used by dispatch.
- Minimal touch points: router helper plus two existing room dispatch branches in `continue_room_round` and `run_room`.
Cons:
- `select_mode` currently returns only `CLARIFY|CONSENSUS|EXECUTE`; implementation must keep that API stable and add a side helper or structured decision without breaking callers.
- Room turn dispatch already has explicit `consensus_mode` and `turn_profile`; precedence must be tested to avoid double-routing.
Invalidation: reject if existing room dispatch cannot consume router output without changing approval or consensus FSM semantics. Inspection shows dispatch already chooses `run_consensus_agent_rounds` versus `run_agent_rounds` from `consensus_mode`, so it is viable.

### Opt-B: thin policy module delegated by `select_mode`
Pros:
- Separates mapping logic into a testable module.
- Can keep `select_mode` small while still delegating from it.
Cons:
- Borderline new routing layer; maintainers could accidentally call the policy directly and fork semantics.
- More files and naming surface for a deterministic rule table.
Invalidation: choose only if `mode_router.py` becomes unwieldy or if several non-room consumers need the same structured decision. Not true for this scope.

### Opt-C: minimal execute-first solo only
Pros:
- Lowest change size and easiest OFF-parity.
- Immediately reduces fanout in the most expensive execution path.
Cons:
- Does not satisfy the approved phase table for DISCUSS/DRAFT/PEER_REVIEW/REFINE/divergence, CLARIFY hybrid, or audit/fresh-eyes requirements.
- Would leave anti-drift requirements mostly unimplemented.
Invalidation: invalid against spec acceptance because phase mapping and audit panel behavior are required.

## In scope / out of scope
In scope:
- Stage-aware routing table and dispatch consumption.
- Flags: `AGENT_LAB_STAGE_ROUTING`, `AGENT_LAB_STAGE_CONTEXT_REINJECT`, `AGENT_LAB_UNANIMITY_REDTEAM`, `AGENT_LAB_FRESH_EYES_AUDIT_CRITIC` registered in `runtime_flags.py` and documented where feature flags are maintained.
- RoutingDecisionLog telemetry as observation only.
- Context re-injection using `clarity.format_facts_block` plus existing ledger/session state summaries.
- Unanimity suspicion red-team round in panel consensus only.
- Fresh-eyes cold critic as a PEER_REVIEW audit panel seat.
Out of scope:
- Dynamic model pool, learned orchestrator, model sovereignty work, behavioral drift-reduction metrics as gates, execute/approval bypasses.

## File-level changes
- `src/agent_lab/mode_router.py`: add flag helper, phase extraction from mission loop and plan workflow, deterministic phase to route table, user override detection interface, structured route helper, and telemetry fields while preserving `select_mode` return type with flags off.
- `src/agent_lab/runtime_flags.py`: register the new default-off flags.
- `src/agent_lab/room_turn_flow.py`: after run_meta is available and turn_profile is recorded, consume the router decision at both `continue_room_round` and `run_room` dispatch points to set effective solo/panel behavior before choosing `run_consensus_agent_rounds` or `run_agent_rounds`.
- `src/agent_lab/room_parallel_rounds.py`: support solo fanout by passing a single selected agent list when the router says solo; retain existing `run_agent_rounds` mechanics.
- `src/agent_lab/context_bundle.py`: add a gated re-injection block in `build_context_bundle` and slim consensus bundle path; use `format_facts_block(run_meta)` plus ledger/session state summaries. Panel stages inject every turn; solo stages only a light once-per-turn block.
- `src/agent_lab/consensus_gate.py` and `src/agent_lab/room_consensus_rounds.py`: detect immediate zero-objection unanimity via normalized `endorse_count`/`agents_consented` and force exactly one red-team round only when route kind is panel and flag is on.
- `src/agent_lab/plan_workflow.py`: add PEER_REVIEW fresh-eyes critic seat under flag inside `run_plan_peer_review_round`, reusing the existing read-only peer-review call pattern with cold context containing only original goal/topic and current artifact/plan.md.
- Tests: add focused tests listed below; update existing expectations only where flag-on behavior is intentionally asserted.

## Sequencing and dependencies
1. Router contract and flags. Add default-off flags to `runtime_flags.py`. In `mode_router.py`, keep `Mode = CLARIFY|CONSENSUS|EXECUTE` and current `select_mode(run)` behavior unchanged when `AGENT_LAB_STAGE_ROUTING` is off. Add a structured helper such as `select_route_decision(run, *, turn_profile=None)` that returns legacy mode plus `route_kind=solo|panel|hybrid`, phase source, override status, and reason. OFF-parity guarantee: `select_mode` returns exactly current values when flag off.
2. Phase extraction. Read mission phase from `run["mission_loop"]["phase"]`; when plan workflow is active, read `plan_workflow.phase` via existing data shape and map `DRAFT`, `PEER_REVIEW`, `REFINE`, `HUMAN_PENDING`, `APPROVED`. Dependency: do not import or mutate `plan_workflow._mirror_verified_loop_status` or approval helpers. OFF-parity: extraction is unused unless stage routing flag is on.
3. Rule table. Implement table: solo for mission `EXECUTE_QUEUE`, `DRY_RUN`, `MERGE_REVIEW`, `VERIFY`, `REPAIR`, quick, scribe; panel for `DISCUSS`, plan `DRAFT`, `PEER_REVIEW`, `REFINE`, divergence; CLARIFY hybrid defaults to solo clarity engine unless ambiguity remains high, then panel. Keep `PLAN_GATE`/`HUMAN_PENDING` non-executing and never bypass gates. OFF-parity: table ignored when flag off.
4. User override precedence. Define explicit override profiles using existing `turn_modes.py` vocabulary: `quick` forces solo; `team`, `loop`, `free`, `review`, `verified`, `specialist`, `divergence` force their existing fanout/topology. Record `override=True` in decision. OFF-parity: existing `turn_profile` handling remains active with flag off.
5. Dispatch consumption. In `room_turn_flow.py`, after `_set_active_turn_flags` and after `turn_profile` normalization, compute route decision and adjust only local effective values: solo means pass `active_agents[:1]`, `parallel_rounds=1`, `consensus_mode=False`, `review_mode=False`; panel means preserve or enable panel/consensus where current mode supports it; hybrid CLARIFY keeps clarifier questions path and only panels when router says ambiguous panel. Apply in both `continue_room_round` and `run_room`. OFF-parity: no call or no mutation when flag off.
6. RoutingDecisionLog telemetry. Extend `record_mode_route` or add a sibling writer in `mode_router.py` that stores an additive `routing_decision_log` row in run_meta and emits trace/on_event when available. Include phase, source, route_kind, override, flags, reason, selected fanout. Observation only; tests assert presence only in telemetry tests, not acceptance gates for behavior. OFF-parity: do not create log when flag off unless existing `mode_route` already would.
7. A: state-externalization re-injection. In `context_bundle.py`, add a helper that composes `format_facts_block(run_meta)` with concise goal ledger/session ledger summaries already present in run_meta. In panel stages under `AGENT_LAB_STAGE_CONTEXT_REINJECT`, append it to constraints every turn. In solo stages append a light block once per human turn or mark with run_meta/context meta to avoid repetition. OFF-parity: helper not called when flag off; existing clarity facts injection remains unchanged.
8. B: unanimity suspicion red-team. In `room_consensus_rounds.py`, at the `not pending` consensus-reached path before returning success, detect immediate zero-objection unanimity: no open objections, all non-anchor active agents consented, and no prior red-team marker for this human turn. If `AGENT_LAB_UNANIMITY_REDTEAM` and route_kind is panel, call one red-team agent round with a follow-up that asks for strongest objection, then re-evaluate consensus once. Never run in solo or non-consensus dispatch. Store a turn marker to prevent loops. OFF-parity: current consensus path unchanged when flag off.
9. Fresh-eyes audit critic seat. In `plan_workflow.py::run_plan_peer_review_round`, when phase is `PEER_REVIEW` and `AGENT_LAB_FRESH_EYES_AUDIT_CRITIC` is on, append a reviewer seat using the ralplan fresh architect/critic per-pass-spawn pattern: cold context contains only original goal/topic, current `plan.md` artifact, and review rubric; exclude chat history, peer discussion, and accumulated facts except explicit goal/artifact. Fold result into existing peer review messages/objections rather than a separate periodic injection. OFF-parity: reviewer set and context unchanged when flag off.
10. Approval spine guard. Add tests that monkeypatch or snapshot `plan_workflow._mirror_verified_loop_status` and `approve_plan` behavior and verify stage routing never calls approve or changes HUMAN_PENDING/APPROVED transitions. No product code edits in those functions. OFF-parity: existing approval tests still pass unmodified.
11. Documentation and registry. Update `.env.example` and docs feature flag section only after implementation, keeping defaults blank/off and explaining telemetry is observation only.
12. Verification pass. Run focused tests first, then full fast lane and static checks. If fast bucket budget trips due added tests, raise only the test bucket budget, not production behavior.

## Acceptance criteria
AC1 Phase mapping: with `AGENT_LAB_STAGE_ROUTING=1`, deterministic tests prove mission `DISCUSS` and plan `DRAFT|PEER_REVIEW|REFINE` route panel; mission `EXECUTE_QUEUE|DRY_RUN|MERGE_REVIEW|VERIFY|REPAIR` route solo; divergence routes panel; quick/scribe route solo; CLARIFY defaults solo and panels only when ambiguity is high.
AC2 User override wins: explicit turn profiles override default phase routing, including `quick` forcing solo in panel phases and `divergence` forcing panel even when phase would otherwise be solo.
AC3 OFF-parity independent flags: with all new flags off, `select_mode`, `record_mode_route`, dispatch fanout, context payload, consensus completion, and plan peer review match current behavior. Each new flag has an independent off-parity regression test.
AC4 Dispatch uses router, not a new layer: tests prove `room_turn_flow` consumes `mode_router` decision and no separate policy module or duplicate phase table is introduced outside router tests.
AC5 A re-injection: with `AGENT_LAB_STAGE_CONTEXT_REINJECT=1`, panel stages include established facts plus ledger block every turn; solo stages include only a light once-per-turn block; flag off preserves existing context text.
AC6 B red-team panel-only: with `AGENT_LAB_UNANIMITY_REDTEAM=1`, immediate zero-objection unanimity in a panel consensus stage triggers exactly one red-team round before consensus finalizes; solo routes and flag-off routes never trigger it.
AC7 Fresh-eyes cold critic: with `AGENT_LAB_FRESH_EYES_AUDIT_CRITIC=1` in `PEER_REVIEW`, a fresh critic seat participates with context limited to original goal/topic plus current artifact/plan; no chat history or prior panel content is included.
AC8 RoutingDecisionLog observational: telemetry records decision facts when enabled, but no test treats telemetry as a behavioral acceptance gate and no gate reads it for approval.
AC9 Approval spine untouched: `_mirror_verified_loop_status`, `approve_plan`, `ensure_plan_workflow_approved`, and execute/merge gates are not modified except import-safe references in tests; existing plan approval tests stay green.
AC10 Dynamic pool deferred: no learned orchestrator, dynamic model pool, sovereignty routing, or model-selection training is implemented; tests or review checklist assert absence of new dynamic routing flag or module.
AC11 CLARIFY unification preserved: server clarifier/clarity engine path remains the default CLARIFY solo scorer; panel CLARIFY only occurs behind stage routing and ambiguity condition.

## Verification
Focused tests to add or extend:
- `tests/test_stage_routing_mode_router.py`: phase table, CLARIFY hybrid, user override precedence, RoutingDecisionLog shape, off-parity for `select_mode`.
- `tests/test_stage_routing_room_dispatch.py`: `continue_room_round` and `run_room` choose single versus panel at the existing dispatch sites and preserve explicit profiles.
- `tests/test_stage_context_reinject.py`: context bundle re-injection in panel every turn, solo light once, flag-off exact absence.
- `tests/test_unanimity_redteam.py`: panel-only one-shot red-team trigger, no solo trigger, no repeated firing.
- `tests/test_fresh_eyes_audit_critic.py`: PEER_REVIEW extra cold critic seat and cold context constraints.
- `tests/test_stage_routing_approval_spine.py`: approval functions untouched and no bypass of HUMAN_PENDING/APPROVED.
Commands:
1. Focused: `pytest tests/test_stage_routing_mode_router.py tests/test_stage_routing_room_dispatch.py tests/test_stage_context_reinject.py tests/test_unanimity_redteam.py tests/test_fresh_eyes_audit_critic.py tests/test_stage_routing_approval_spine.py`
2. Fast lane: `make test-fast` noting fast-bucket budget may need raising only for deterministic added tests.
3. Static: `ruff check src/agent_lab tests`, `ruff format --check src/agent_lab tests`, `mypy src/agent_lab/mode_router.py src/agent_lab/room_turn_flow.py src/agent_lab/context_bundle.py src/agent_lab/room_consensus_rounds.py src/agent_lab/consensus_gate.py src/agent_lab/plan_workflow.py src/agent_lab/runtime_flags.py`.

## Risks and mitigations
1. Flag-combination matrix risk: independent flags can interact unexpectedly. Mitigate with matrix tests for all off, routing only, reinject only, red-team only, fresh critic only, and all on.
2. Dispatch entanglement risk: single-vs-panel is currently implied by `consensus_mode`, `parallel_rounds`, `turn_profile`, and agent list. Mitigate by consuming router output only at the two existing dispatch sites and by avoiding duplicate phase tables outside `mode_router.py`.
3. B over-firing risk: unanimity red-team could loop or punish normal consensus. Mitigate with panel-only guard, zero-objection/immediate-unanimity condition, per-turn fired marker, and exactly one extra round.
4. Cost/context risk: facts/ledger re-injection and fresh critic add tokens and calls. Mitigate with concise capped blocks, solo light mode, default-off flags, and tests that assert cold critic is only PEER_REVIEW.
5. CLARIFY unification risk: recent clarity engine/server clarifier work could be bypassed. Mitigate by making CLARIFY hybrid default to solo scorer and preserving `plan_workflow_skips_server_clarifier` behavior.
6. Approval-spine bypass risk: EXECUTE solo routing might appear to authorize execution. Mitigate by documenting router as classification only, not approval, and by testing `ensure_plan_workflow_approved` and `approve_plan` remain the only approval path.
7. Telemetry misuse risk: RoutingDecisionLog could become a gate. Mitigate by keeping it additive, write-only observation and adding review checklist/AC that no gate reads it.

## RALPLAN-DR summary
Principles: extend-not-layer, OFF-parity, user-override-wins, mechanism tests as gate, approval-spine untouched.
Drivers: preserve semantics, deterministic/observable routing, low-risk anti-drift.
Options: Opt-A selected: router table consumed by existing dispatch. Opt-B rejected as near-new layer until complexity proves necessary. Opt-C rejected because execute-only solo fails the approved scope.
Decision: implement Opt-A with independent default-off guards for stage routing, context re-injection, unanimity red-team, and fresh-eyes audit critic.
