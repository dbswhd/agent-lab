## Summary
Opt-B is directionally the right long-term architecture: A owns the public clarifier contract, C owns scoring and adaptive questions, and B remains the plan-workflow gate. The draft is not execution-ready: plan workflow explicitly skips the A server-clarifier surface while the proposed B clarity gate can hold CLARIFY without surfacing C-backed questions, and the moved persistence guard can desynchronize UI or SSE prompts from run.json.

## Analysis
Evidence inspected:
- src/agent_lab/session_clarifier.py: ClarifierCategory currently allows only goal, scope, verify, constraints, priority; _question is typed against that set; build_clarifier_interview builds the v2 public shape; persist_clarifier_interview unconditionally writes run clarifier_interview; public read and answer update paths are public_clarifier_interview, record_clarifier_answers, and sync_clarifier_answers_from_inbox.
- src/agent_lab/clarity.py: CLARITY_DIMENSIONS are goal, constraints, criteria, context; lateral_questions emits those categories and internally calls score_clarity; ensure_clarify_questions already has the non-complete guard and persists via session_clarifier; clarity_threshold_met folds answered Q and A into the scored text.
- src/agent_lab/plan_workflow.py: plan_workflow_skips_server_clarifier returns is_plan_workflow_active; _mirror_verified_loop_status and approve_plan are the approval and status spine; tick_plan_workflow_after_turn currently advances CLARIFY by inbox-empty plus round counter.
- src/agent_lab/room_turn_flow.py: both initial and continuation Room paths skip A when plan workflow is active; otherwise they build, persist, and emit clarifier_prompt SSE.
- src/agent_lab/mission_advance.py: C question generation is reached only for mission-loop CLARIFY, not plan-workflow CLARIFY.
- src/agent_lab/mission_loop.py: pipeline_enabled is default-on with explicit 0 or false opt-out. The Planner wording about AGENT_LAB_PIPELINE default-off semantics contradicts this.
- src/agent_lab/runtime_flags.py: AGENT_LAB_CLARIFIER and AGENT_LAB_CLARIFIER_INTERVIEW are registered; AGENT_LAB_CLARIFIER_ENGINE is not.
- web/src/components/RoomChat.tsx: the UI treats question category as an optional string and displays it raw, so criteria and context are a public expansion but not a frontend enum break.

Spec compliance: the draft preserves the single run.json clarifier_interview store and keeps _mirror_verified_loop_status plus approve_plan intact. It also intends to preserve C anchor-skip and mock determinism. It fails execution-readiness on plan-workflow reachability, persistence guard semantics, category contract specificity, and exact OFF-parity proof obligations.

### Strongest steelman antithesis against Opt-B
The best case against Opt-B is that this is a Phase-0-style pilot but adds a new module, a new flag, a new category bridge, and a new import edge before the behavior has been proven. Opt-A would be safer for a pilot because the two A call sites in room_turn_flow.py are already the only live SSE and inbox path for the server clarifier; local flag-gated C calls there would make reachability obvious and avoid a new adapter. Opt-C would be safest if the urgent defect is only the write race: fix idempotency narrowly and leave public categories, scoring cost, and plan-workflow advancement untouched.

The strongest antithesis is around state-machine and import edges. C already imports A lazily for persistence, so A to adapter to C plus C to adapter or A can form a fragile cycle unless the adapter is strictly lazy and pure. More importantly, a new adapter can hide the fact that there are two human surfaces: A server-clarifier SSE or T-Q0, and plan_workflow ask_human or inbox. A module is premature unless it removes duplicated policy without making plan-workflow questions less reachable.

### Synthesis
Opt-B is still the better target if narrowed. Make clarifier_engine.py a pure shape and flag adapter with lazy imports and no storage; keep persistence semantics in A; and explicitly wire B false-threshold handling to a reachable human surface. This preserves the Phase-0 safety of Opt-A or Opt-C while giving the system one category and interview construction contract.

## Root Cause
The plan conflates A owning the clarifier contract with A server-clarifier delivery being reachable. In source, plan workflow disables the A delivery path, while C ensure_clarify_questions belongs to mission-loop CLARIFY. That leaves no owner for delivering C questions when B decides plan-workflow CLARIFY is still ambiguous.

## Findings
1. BLOCKING — B clarity gate can strand plan_workflow CLARIFY without a reachable question surface.
   - Reference: Planner step 6; src/agent_lab/plan_workflow.py::tick_plan_workflow_after_turn; src/agent_lab/plan_workflow.py::plan_workflow_skips_server_clarifier; src/agent_lab/room_turn_flow.py server-clarifier blocks; src/agent_lab/mission_advance.py CLARIFY branch.
   - Impact: When plan workflow is active, A build, persist, SSE, and T-Q0 paths are skipped. Step 6 proposes holding CLARIFY when clarity_threshold_met is false, but it does not create visible questions. ensure_clarify_questions is not automatically reached by plan_workflow. Result: silent clarity_pending or CLARIFY hold with no answer path.
   - Fix: Amend B false-threshold handling so holding CLARIFY requires a visible pending question. Use a shared C-to-A builder plus Human Inbox harvest or fan-out, or allow engine-backed A in plan-workflow CLARIFY, or route C questions through plan_workflow ask_human. Add a test where plan_workflow remains CLARIFY only because a pending visible question exists.

2. HIGH — Category contract is unresolved and can break typing or semantics.
   - Reference: Planner steps 2, 3, 5 and AC2, AC7; src/agent_lab/session_clarifier.py::ClarifierCategory; src/agent_lab/clarity.py::CLARITY_DIMENSIONS and lateral_questions; web/src/components/RoomChat.tsx rendering.
   - Impact: C emits criteria and context, but A excludes them from its Literal. Preserving C categories without extending the Literal risks mypy errors if A helpers are used. Mapping criteria to verify and context to scope avoids the type issue but loses the dimensions that C scores and that facts should preserve.
   - Fix: Choose explicitly. Recommended: extend the v2 Literal to include criteria and context, preserve the C dimension, and add display or legacy labels only if needed. This is additive and OFF-parity safe because engine-off outputs do not change. Add mypy and public-contract tests.

3. HIGH — Moving the non-complete guard into persist_clarifier_interview is too broad unless return and replacement semantics are specified.
   - Reference: Planner step 4 and AC4; src/agent_lab/session_clarifier.py::persist_clarifier_interview; src/agent_lab/room_turn_flow.py call sites; src/agent_lab/clarity.py::ensure_clarify_questions existing guard.
   - Impact: If persistence silently no-ops on an existing pending interview but returns the incoming candidate, SSE can show questions that are not in run.json, so answer harvesting targets old prompts. A blanket guard can also block same-source metadata updates, refined prompts with stable ids, or controlled admin and test replacements.
   - Fix: Make persist return the actual persisted interview or a structured result with persisted and reason fields. Define identity-aware replacement: block cross-source pending replacement by default, allow same-id and same-source metadata updates, keep completion in record_clarifier_answers, and require explicit replacement for controlled cases. Room flow must emit prompts from persisted state.

4. HIGH — Pipeline default semantics and flag matrix are wrong or incomplete.
   - Reference: Planner Principles, AC1, AC9; src/agent_lab/mission_loop.py::pipeline_enabled; pipeline scaffold tests; src/agent_lab/runtime_flags.py.
   - Impact: Source makes AGENT_LAB_PIPELINE default-on with explicit opt-out. The draft says default-off, which can lead implementers to break current dogfood behavior. The matrix must also define CLARIFIER=0, CLARIFIER_ENGINE=1, PIPELINE=1, and plan_workflow active; B must not gate without some reachable surface.
   - Fix: Correct the wording, preserve current pipeline default-on behavior, register AGENT_LAB_CLARIFIER_ENGINE default-off, and test CLARIFIER off plus engine on with plan_workflow active and inactive.

5. MEDIUM — Adapter sequence can double live panel and topology cost.
   - Reference: Planner step 2; src/agent_lab/clarity.py::score_clarity, lateral_questions, and score_components; src/agent_lab/room_turn_flow.py short and first-turn triggers.
   - Impact: Step 2 says the adapter calls both score and lateral questions, but lateral_questions already scores. Live mode can double the intended panel calls before agents run. The engine flag limits blast radius but not enabled-session cost.
   - Fix: Expose lateral_questions_from_result or return result plus questions from one C call. Add live-call-count tests with topology off and on.

6. MEDIUM — OFF-parity criteria are not precise enough.
   - Reference: Planner AC1, AC7, AC9; room_turn_flow SSE; session_clarifier.public_clarifier_interview; clarifier HTTP routes; runtime snapshot; inbox_harvest.harvest_clarifier_questions; plan_workflow_complete_payload.
   - Impact: Existing tests passing is not a byte-stability proof. This feature touches SSE payloads, run.json, HTTP envelopes, runtime snapshots, T-Q0 inbox items, and plan-workflow complete payloads. Timestamped outputs need frozen time or normalized comparisons.
   - Fix: Add explicit OFF-parity boundary tests for SSE payload bytes, run.json clarifier_interview, GET and POST clarifier endpoints, runtime snapshot, T-Q0 inbox item fields, no new plan_workflow clarity fields when engine off, and absence of a parallel store.

7. LOW — Adapter import boundary must be enforceable.
   - Reference: Planner Opt-B and Risk 5; src/agent_lab/clarity.py::ensure_clarify_questions lazy imports from A.
   - Impact: Lazy import guidance is correct but not enough. Top-level A to adapter to C combined with any top-level C to adapter or A import can produce cycles.
   - Fix: Specify no top-level imports between A, C, and adapter except under type checking; C imports inside functions; adapter has no storage writes. Add import smoke tests.

## Recommendations
1. Revise step 6: B must not hold CLARIFY unless C-backed questions are visible through SSE, HTTP or runtime state, or Human Inbox.
2. Revise step 4: persistence guard must return persisted state and define identity and replacement policy.
3. Resolve category shape by extending the v2 Literal with criteria and context, or by mapping only with a separate preserved C dimension.
4. Correct AGENT_LAB_PIPELINE wording and add AGENT_LAB_CLARIFIER_ENGINE to the flag registry as default-off.
5. Avoid duplicate scoring in the adapter and prove the live-call bound.
6. Expand ACs with exact OFF-parity and no-stranding tests.

## Architectural Status
BLOCK

## Code Review Recommendation
REQUEST CHANGES

## Trade-offs
| Option | Benefit | Risk | Recommended use |
| --- | --- | --- | --- |
| Opt-A direct C calls at A call sites | Small pilot footprint and obvious live surface | Duplicates policy across Room paths and leaves C.ensure divergent | Accept only as a short spike |
| Opt-B thin adapter | Best long-term boundary and one construction contract | New import edge, category bridge, hidden surface gap unless fixed | Preferred after blocking fixes |
| Opt-C race fix only | Safest immediate defect fix | Does not unify CLARIFY or B gating | Useful first patch, insufficient for target |

Real tension: centralized persistence guard versus legitimate pending-interview replacement. Centralizing in A reduces clobber risk, but a broad guard can silently no-op callers and diverge UI from durable state. Resolve by making the guard identity-aware and observable.

Second tension: semantic fidelity versus legacy category vocabulary. Mapping criteria and context to verify and scope preserves old labels but loses C dimensions. Resolve by extending v2 categories under the engine flag and adding display labels only where needed.

## Verdict on Acceptance Criteria
- AC1: Testable but insufficient. It must preserve current pipeline default-on plus explicit-off behavior.
- AC2: Testable but ambiguous until category Literal and mapping policy are chosen.
- AC3: Insufficient. It proves hold and advance but not that held CLARIFY has visible questions.
- AC4: Necessary but incomplete. Add same-source update, persisted-return, and SSE versus run.json consistency cases.
- AC5: Good, but assert no persisted interview, inbox, or SSE prompt for anchored tasks.
- AC6: Good for mock determinism, but missing live-call-count bounds.
- AC7: Necessary but should be split into exact HTTP, runtime snapshot, run.json, inbox, and SSE contract tests.
- AC8: Good. Keep approve_plan as the only APPROVED or running transition.
- AC9: Necessary but underspecified. Include CLARIFIER off plus ENGINE on, PIPELINE explicit off, pipeline default-on, plan_workflow active and inactive, and no stranded CLARIFY.

Missing ACs:
- AC10: B false-threshold hold creates or references at least one human-visible pending question, or does not hold.
- AC11: Category contract is typed, mypy-clean, and public-contract tested for criteria and context.
- AC12: persist_clarifier_interview returns actual persisted state and room_turn_flow emits only persisted prompts.
- AC13: Engine-backed A performs at most one C panel scoring pass per turn, with topology bounded as documented.
- AC14: OFF-parity boundary tests cover SSE bytes, run.json, HTTP envelopes, runtime snapshot, T-Q0 inbox, and plan_workflow complete payload.
- AC15: AGENT_LAB_CLARIFIER_ENGINE appears in the flag registry and /api/health/flags with default off.
