# Planner Draft: Unify agent-lab CLARIFY Subsystems

## Summary
Unify CLARIFY by making C, src/agent_lab/clarity.py, the intelligent engine; A, src/agent_lab/session_clarifier.py plus its existing UI/HTTP/SSE/inbox/snapshot wiring, the single human question surface; and B, src/agent_lab/plan_workflow.py, the execution gate that advances only when the C clarity threshold is met under the opt-in path. Recommended option: Opt-B, a thin adapter used by A and C, because it centralizes question-shape and persistence policy while keeping existing call sites and OFF behavior stable.

## Principles
1. Single source of truth: run.json clarifier_interview remains the only durable interview store; no parallel clarity-question store.
2. OFF-parity first: with new flags unset, AGENT_LAB_CLARIFIER, AGENT_LAB_PIPELINE, and plan_workflow behavior remains byte-for-byte equivalent at observable boundaries.
3. Additive flag-gating: C-backed A questions and B clarity gating require explicit opt-in, proposed AGENT_LAB_CLARIFIER_ENGINE=1, and retain existing AGENT_LAB_CLARIFIER and AGENT_LAB_PIPELINE default-off semantics.
4. Layering: A is the stable question surface and contract owner; B is the plan execution gate; C is the scoring and adaptive-question engine.
5. Preserve contracts: A HTTP endpoints, SSE clarifier_prompt payload, snapshot field, inbox T-Q0 harvest, record_clarifier_answers completion, B _mirror_verified_loop_status, and approve_plan remain the integration spine.

## Decision Drivers
1. Safety across flag combinations: CLARIFIER x CLARIFIER_ENGINE x PIPELINE x plan_workflow must not strand sessions, clobber interviews, or bypass approval.
2. Minimal contract churn: existing UI/HTTP/inbox/snapshot consumers must keep the same interview dict shape and storage field.
3. Intelligence without cost surprises: live C panel calls should be bounded, mock-safe, and avoid duplicate scoring per turn where possible.

## Viable Options
### Opt-A: Inject C-backed generation at room_turn_flow A call sites
Change the two room_turn_flow server-clarifier blocks, around run_room and continue_room_round, so when AGENT_LAB_CLARIFIER_ENGINE=1 they call C score_clarity/lateral_questions or a helper before falling back to A build_clarifier_interview; move the idempotent non-complete guard into A persist_clarifier_interview.
Pros: smallest implementation footprint; no new module; localizes behavior to the existing A trigger points; easy OFF-parity by guarding only in room_turn_flow.
Cons: duplicates policy across two call sites; C.ensure_clarify_questions still has separate construction logic; harder to keep A and C question-shape normalization identical; more likely to diverge between plan_mode/discuss paths.
Invalidation rationale: acceptable as a tactical patch, but it leaves the same conceptual split that caused the race and makes future topology/question-shape changes more fragile.

### Opt-B: Thin adapter module used by A and C, with A owning persistence guard (chosen)
Add a narrow adapter, e.g. src/agent_lab/clarifier_engine.py, that exposes engine_enabled(), build_engine_interview(text, is_new_session, human_message_count, plan_mode, run=None), and normalize C lateral_questions into A interview v2 shape. A build_clarifier_interview consults this adapter when CLARIFIER and CLARIFIER_ENGINE are on; C.ensure_clarify_questions also uses the adapter or shared builder for interview construction. A persist_clarifier_interview adopts the non-complete guard.
Pros: one place maps C questions to A contract; minimizes room_turn_flow edits; keeps C scoring APIs intact; preserves existing A surface; lowers race and divergence risk; makes tests easier and more focused.
Cons: adds one small module and a dependency edge from A to adapter to C; must avoid import cycles by importing lazily; slightly more design surface than Opt-A.
Justification: best balance of maintainability and low behavioral blast radius. It honors A=surface/B=gate/C=engine layering and gives both A and C one shared construction path without changing public contracts.

### Opt-C: Do nothing except fix the persist race
Move C's non-complete guard into A persist_clarifier_interview and leave A static questions plus B round/inbox heuristic unchanged.
Pros: lowest risk and fastest; eliminates clobbering; preserves all existing behavior.
Cons: does not satisfy C-backed A questions; B still ignores real ambiguity; leaves three CLARIFY systems semantically separate.
Invalidation rationale: useful prerequisite but not a unification; fails the target architecture and acceptance criteria.

## In scope / out of scope
In scope: flag-gated C-backed A questions; B CLARIFY advancement gated on C clarity; A persist race fix; tests for flag matrix, contracts, and mock determinism.
Out of scope: changing HTTP routes, UI payload shape, inbox item schema, snapshot schema beyond existing clarifier_interview content, approval semantics, or live agent registry behavior.

## File-level changes
- src/agent_lab/session_clarifier.py: add CLARIFIER_ENGINE flag helper or import from adapter; build_clarifier_interview uses adapter first under AGENT_LAB_CLARIFIER_ENGINE=1 and falls back to current static logic; persist_clarifier_interview preserves existing non-complete interviews unless explicitly allowed by completion/write semantics.
- src/agent_lab/clarity.py: keep score_clarity, lateral_questions, clarity_threshold_met, anchor skip, topology, and mock behavior; change ensure_clarify_questions to use the shared adapter/builder and rely on A's guarded persist rather than duplicating persistence policy.
- src/agent_lab/plan_workflow.py: in tick_plan_workflow_after_turn CLARIFY branch, when AGENT_LAB_PIPELINE and AGENT_LAB_CLARIFIER_ENGINE are on, read current run and require clarity_threshold_met(run) before DRAFT; keep has_pending_inbox_question hold and _mirror_verified_loop_status unchanged.
- src/agent_lab/room_turn_flow.py: leave the two server-clarifier blocks structurally intact; they continue calling build_clarifier_interview and persist_clarifier_interview, gaining C-backed questions through A's builder under the new flag.
- src/agent_lab/mission_advance.py: keep the CLARIFY branch calling clarity_threshold_met and ensure_clarify_questions; verify it remains compatible with the shared builder and A guard.
- New optional file src/agent_lab/clarifier_engine.py: thin adapter only; no storage; lazy imports from clarity to avoid cycles.

## Sequencing and dependencies
1. Add AGENT_LAB_CLARIFIER_ENGINE flag helper in the adapter or session_clarifier.py. Additive change: default false. Gating flag: AGENT_LAB_CLARIFIER_ENGINE plus existing AGENT_LAB_CLARIFIER for A surface. OFF-parity: unset flag leaves build_clarifier_interview on current static templates.
2. Implement the thin adapter build_engine_interview. It calls clarity.score_clarity and clarity.lateral_questions(text, max_q=3 or existing cap), preserves C anchor skip by returning None when no questions are produced, and returns A's exact interview v2 dict shape with version/status/human_turn/questions/answers/created_at/plan_mode plus source=clarify_panel or clarity_engine. Gating flag: caller checks AGENT_LAB_CLARIFIER_ENGINE. OFF-parity: no call when off, so no panel cost or shape change.
3. Update src/agent_lab/session_clarifier.py build_clarifier_interview. Additive change: after existing clarifier_enabled/text checks and before static template selection, when engine flag is on call the adapter; if it returns questions, return that interview; if it returns None, fall through to existing static logic only where current logic would ask. Gating flag: AGENT_LAB_CLARIFIER_ENGINE. OFF-parity: flag off follows existing code path exactly.
4. Resolve the write race in src/agent_lab/session_clarifier.py persist_clarifier_interview. Additive change: read existing clarifier_interview inside patch; if existing is a dict and status != complete, return run unchanged, unless the incoming write is the same open interview update or an explicit replace mode is introduced for tests/admin only. Keep record_clarifier_answers separate and unchanged so answering all questions still sets status=complete and completed_at. Gating flag: none, because this is safety/idempotency; OFF-parity concern is limited to preventing unintended clobber only, not changing successful answer completion.
5. Update src/agent_lab/clarity.py ensure_clarify_questions. Additive change: use the adapter/shared builder to construct the interview from lateral_questions and keep the early existing non-complete return. Gating flag: existing AGENT_LAB_PIPELINE in mission_advance controls execution; adapter can be used regardless inside C because ensure_clarify_questions is already pipeline-gated by callers. OFF-parity: pipeline off never calls it; pipeline on retains anchor skip and mock-safe deterministic questions.
6. Update src/agent_lab/plan_workflow.py tick_plan_workflow_after_turn CLARIFY branch. Additive change: after has_pending_inbox_question is false and before incrementing clarify_round/advancing to DRAFT, if AGENT_LAB_PIPELINE and AGENT_LAB_CLARIFIER_ENGINE are on, call clarity_threshold_met(read_run_meta(folder)); if false, keep phase CLARIFY, set wait_inbox or clarity_pending metadata and avoid DRAFT. Gating flag: AGENT_LAB_CLARIFIER_ENGINE plus AGENT_LAB_PIPELINE and active plan_workflow. OFF-parity: with either flag off, existing round-counter/inbox-empty heuristic remains unchanged.
7. Keep _mirror_verified_loop_status and approve_plan unchanged. Additive change: none except tests proving HUMAN_PENDING still maps to pending_approval and APPROVED to running. Gating flag: none. OFF-parity: no execution-gate regression.
8. Leave src/agent_lab/room_turn_flow.py call sites mostly intact. Additive change: no direct C imports; they still call A build/persist in both initial and continuation server-clarifier blocks, so UI/SSE event and delegate short-circuit behavior remain unchanged. Gating flag: inherited through A. OFF-parity: unchanged blocks produce current static prompts.
9. Leave src/agent_lab/mission_advance.py CLARIFY branch structurally unchanged. Additive change: only adjust imports/calls if ensure_clarify_questions signature changes. Gating flag: existing AGENT_LAB_PIPELINE. OFF-parity: pipeline disabled still returns pipeline_disabled; anchor-skip still advances to DISCUSS.
10. Add focused tests before broad verification. Dependencies: race guard tests first, then A engine-surface tests, B gate tests, mission_advance regression tests.

## Acceptance criteria
AC1, steps 1/3/6/8/9: With AGENT_LAB_CLARIFIER_ENGINE unset, existing tests for A static question selection, B CLARIFY round advancement, and C pipeline CLARIFY behavior pass without expectation changes.
AC2, steps 1/3/8: With AGENT_LAB_CLARIFIER=1 and AGENT_LAB_CLARIFIER_ENGINE=1, room_turn_flow's existing clarifier_prompt SSE and clarifier_interview payload contain C lateral question ids/categories/prompts in A's v2 interview shape.
AC3, steps 6/7: With plan_workflow active, AGENT_LAB_PIPELINE=1, and AGENT_LAB_CLARIFIER_ENGINE=1, tick_plan_workflow_after_turn remains in CLARIFY when clarity_threshold_met is false and advances through existing DRAFT to HUMAN_PENDING path only after threshold is true; _mirror_verified_loop_status still maps HUMAN_PENDING to pending_approval.
AC4, steps 4/5/8: A persist does not clobber a pending C-created clarifier_interview during a later A turn; after record_clarifier_answers completes it, a subsequent A/C write can create the next pending interview.
AC5, steps 2/5/9: C detect_concrete_anchors still causes score_clarity/clarity_threshold_met to short-circuit and no unnecessary clarifier interview is created for anchored tasks.
AC6, steps 2/5: Under AGENT_LAB_MOCK_AGENTS=1, score_clarity/lateral_questions and A engine-backed build_clarifier_interview are deterministic and do not require live agent calls.
AC7, steps 3/8: HTTP GET/POST /sessions/{id}/clarifier-interview(/answers), runtime snapshot clarifier_interview, inbox T-Q0 harvest, sync_clarifier_answers_from_inbox, and record_clarifier_answers continue using the same run.json field and public shape.
AC8, steps 6/7: approve_plan remains the single transition to APPROVED/running execution; clarity gating never starts execution directly.
AC9, steps 1/6: Flag matrix tests cover CLARIFIER, CLARIFIER_ENGINE, PIPELINE, and plan_workflow active/inactive combinations without stranded CLARIFY or duplicate interview stores.

## Verification
Focused tests to add or update:
- tests/test_session_clarifier.py: engine flag off static parity; engine flag on C-backed questions; persist non-complete guard; record_clarifier_answers completion still works.
- tests/test_clarity.py: adapter/shared builder preserves anchor skip, lateral question order, mock determinism, and ensure_clarify_questions idempotency.
- tests/test_plan_workflow.py: CLARIFY branch gates on clarity_threshold_met only when PIPELINE and CLARIFIER_ENGINE are on; existing round cap behavior remains when off; _mirror_verified_loop_status unchanged.
- tests/test_room_turn_flow.py or existing room flow test file: both initial and continuation server-clarifier blocks emit unchanged SSE/public payload shape while using C-backed questions under the flag.
- tests/test_mission_advance.py: pipeline CLARIFY branch still calls ensure_clarify_questions when ambiguous and advances to DISCUSS when clarity_threshold_met is true.

Commands:
1. Run the focused tests above first.
2. Run make test-fast. Note: the fast-bucket budget may need raising because engine-backed A tests can exercise C scoring paths.
3. Run ruff check on changed files.
4. Run ruff format --check on changed files.
5. Run mypy on changed files or the project mypy target if that is the repository convention.

## Risks and mitigations
1. Flag-combination matrix risk: CLARIFIER off but CLARIFIER_ENGINE on could unexpectedly produce interviews. Mitigation: A checks clarifier_enabled first; B clarity gate requires PIPELINE plus engine; tests enumerate combinations.
2. Write-race risk: A static/engine turn overwrites C pending interview before answers land. Mitigation: move non-complete guard into A persist, test C pending survives A turn, keep record_clarifier_answers as the only completion writer.
3. plan_mode vs discuss divergence: C lateral questions have goal/constraints/criteria/context categories while A plan/discuss templates use goal/scope/verify/constraints/priority. Mitigation: adapter normalizes categories to A-accepted v2 fields or deliberately extends the Literal if needed with tests for both synthesize=True and False.
4. Live-panel cost risk: every A turn could trigger up to three C scoring calls, plus topology when enabled. Mitigation: new engine flag default off; call C only when A would otherwise consider asking; cap max_q and panel as C already does; avoid duplicate score_clarity plus lateral_questions calls if adapter can reuse result in a follow-up optimization.
5. Import-cycle risk: A importing C while C imports A persist functions could cycle. Mitigation: use a tiny adapter with lazy imports or local imports inside functions; keep storage writes in A only.
6. Gate deadlock risk: B holds CLARIFY on clarity_threshold_met false without surfacing questions. Mitigation: when holding, rely on A surface if CLARIFIER is on and C.ensure_clarify_questions under PIPELINE; tests assert either pending questions exist or the gate metadata explains clarity_pending.
7. Contract regression risk: modifying interview construction could break HTTP/snapshot/inbox clients. Mitigation: preserve dict keys and public_clarifier_interview behavior; add contract tests around endpoints/snapshot/inbox harvest where existing fixtures allow.
