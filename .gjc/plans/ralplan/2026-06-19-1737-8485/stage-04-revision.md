# Revision Draft: Unify agent-lab CLARIFY Subsystems

## Summary
Unify CLARIFY by keeping A (`session_clarifier.py` plus HTTP/SSE/snapshot/inbox contracts) as the question surface and single `run.json.clarifier_interview` owner, B (`plan_workflow.py`) as the approval gate, and C (`clarity.py`) as the adaptive engine. Keep Opt-B, narrowed: a pure lazy `clarifier_engine.py` adapter, `AGENT_LAB_CLARIFIER_ENGINE` default-off, B delivery through Human Inbox, identity-aware A persistence, and one-pass C scoring.

## Principles
1. Single store: `run.json.clarifier_interview` is the only durable interview store; no parallel C or B store.
2. Layering: A owns public shape and persistence; B owns plan-workflow gating and approval; C owns scoring, anchor-skip, topology, and adaptive questions.
3. Additive flags: engine behavior is opt-in via `AGENT_LAB_CLARIFIER_ENGINE=1`; `AGENT_LAB_CLARIFIER` gates the normal A surface; `AGENT_LAB_PIPELINE` remains default-ON with explicit false/0 opt-out.
4. Visible-hold invariant: B may hold CLARIFY on unmet clarity only when at least one human-visible pending question exists.
5. Contract stability: HTTP envelopes, SSE payload shape, snapshot fields, T-Q0 inbox fields, `_mirror_verified_loop_status`, and `approve_plan` remain stable.

## Decision Drivers
1. Reachability: every false-threshold CLARIFY hold needs a visible answer and harvest path.
2. OFF-parity: engine-off behavior must be byte-stable at public boundaries with frozen or normalized time.
3. Bounded cost and import safety: engine-backed A uses at most one C panel pass per turn and A/C/adapter imports cannot cycle.

## Viable Options
### Opt-A: Inject C-backed generation at A call sites in `room_turn_flow.py`
Change both server-clarifier blocks so, behind `AGENT_LAB_CLARIFIER_ENGINE`, they call C and persist A-shaped interviews.
Pros: obvious SSE surface when plan_workflow is inactive; small footprint.
Cons: plan_workflow skips the A server-clarifier path, so B reachability is still unsolved unless skip logic also changes; construction policy duplicates across two blocks; `clarity.ensure_clarify_questions` remains divergent.
Invalidation: useful spike, not the durable unification.

### Opt-B: Pure adapter used by A and C, B routes false-threshold questions through Human Inbox (chosen)
Add `src/agent_lab/clarifier_engine.py` as a pure adapter for flags, category shape, and one-pass C question generation. A calls it from `build_clarifier_interview` only when both A clarifier and engine are enabled. C may use the adapter for shape, but storage stays in A. B creates or references C-backed questions through Human Inbox when clarity is false.
Pros: one construction contract; solves plan_workflow reachability without weakening `plan_workflow_skips_server_clarifier`; preserves A public surface and B approval; supports call-count tests; avoids cycles via lazy imports.
Cons: adds one small module and Human Inbox delivery tests.
Justification: best satisfies A=surface, B=gate, C=engine. Human Inbox is preferred over allowing the A server-clarifier surface under plan_workflow because B already observes `has_pending_inbox_question` and avoids SSE-only questions that B cannot see.

### Opt-C: Race fix only
Make A persistence idempotent and leave static A questions plus B round-counter behavior unchanged.
Pros: lowest risk for the immediate race.
Cons: no C-backed A questions and no real clarity gate in B.
Invalidation: prerequisite-sized patch, not unification.

## In scope / out of scope
In scope: `AGENT_LAB_CLARIFIER_ENGINE` registry; C-backed A questions; B clarity gating with Human Inbox delivery; category expansion to `criteria` and `context`; identity-aware A persistence; one-pass C scoring; OFF-parity boundary tests.
Out of scope: new frontend enum, new durable store, approval redesign, broad UI redesign, changes to `approve_plan`, changes to `_mirror_verified_loop_status`, or making pipeline default-off.

## File-level changes
- `src/agent_lab/runtime_flags.py`: register `AGENT_LAB_CLARIFIER_ENGINE` as default-off and expose it through `/api/health/flags` with false default.
- `src/agent_lab/session_clarifier.py`: extend `ClarifierCategory` with `criteria` and `context`; call the adapter from `build_clarifier_interview` behind engine flag; replace unconditional persist with identity-aware persist that returns actual persisted state or structured result.
- `src/agent_lab/clarifier_engine.py` (new): pure flag/shape adapter; no storage writes; no top-level imports from A or C except under `TYPE_CHECKING`; lazily imports C inside functions; provides one-pass question generation.
- `src/agent_lab/clarity.py`: keep `score_clarity`, `clarity_threshold_met`, anchor skip, topology, and mock behavior; add `lateral_questions_from_result(result, *, max_q=3)` or equivalent; keep `lateral_questions` as compatible wrapper.
- `src/agent_lab/plan_workflow.py`: in `tick_plan_workflow_after_turn` CLARIFY branch, when pipeline+engine are active and threshold is false, create or reference at least one C-backed Human Inbox question before holding; keep `_mirror_verified_loop_status` and `approve_plan` untouched.
- `src/agent_lab/room_turn_flow.py`: keep both server-clarifier blocks structurally intact; persist first and emit SSE from actual persisted/public state, never from a rejected candidate.
- `src/agent_lab/mission_advance.py`: preserve existing pipeline CLARIFY branch and compatibility with shared builder/persist result.

## Sequencing and dependencies
1. Register `AGENT_LAB_CLARIFIER_ENGINE` in `runtime_flags.py`. Additive: default false, health flags false unless set. OFF-parity: no behavior change when unset.
2. Add pure `clarifier_engine.py` with `engine_enabled()`, `build_engine_interview(...)`, and one-pass `engine_questions(...)` returning `(result, questions)` or equivalent. It writes nothing and lazily imports C. OFF-parity: inert when flag off.
3. Add `clarity.lateral_questions_from_result(result, *, max_q=3)` and update `lateral_questions` to call `score_clarity` once then the helper. Existing API remains; returned questions match current behavior.
4. Extend `session_clarifier.ClarifierCategory` to include `criteria` and `context`. Engine-off static outputs still use existing categories.
5. Update `session_clarifier.build_clarifier_interview`: after `clarifier_enabled()` and text checks, call adapter when engine flag is on. If it returns questions, return A v2 dict with C categories preserved. If no questions due to anchor-skip or threshold met, fall through only where current A would ask. OFF-parity: engine off follows existing branches exactly.
6. Replace unconditional `persist_clarifier_interview` with identity-aware semantics. Return actual persisted state or `{interview, persisted, reason}`. Block cross-source pending replacement by default, allow same-source/same-question-id metadata updates, keep completion solely in `record_clarifier_answers`, and require explicit `replace=True` for controlled replacements.
7. Update both `room_turn_flow.py` blocks: build candidate, persist, derive prompts and SSE from returned persisted/public interview. If replacement is blocked, omit candidate SSE or emit the existing persisted pending interview.
8. Update `clarity.ensure_clarify_questions`: keep early existing non-complete return; use shared shape if useful; call A persist and use returned actual state. Preserve anchor-skip and idempotency.
9. Update `plan_workflow.tick_plan_workflow_after_turn`: if pending inbox exists, keep current hold. Else, when pipeline is enabled and engine is on, evaluate `clarity_threshold_met(read_run_meta(folder))`. If true, continue current DRAFT advance. If false, generate C-backed questions with one-pass helper and create Human Inbox question(s) using existing question fields so `has_pending_inbox_question` will be true. Hold CLARIFY only after confirming at least one pending visible inbox question exists. If engine off or pipeline explicit-off, keep current round-counter behavior.
10. Keep `_mirror_verified_loop_status` and `approve_plan` unchanged; add regression tests for HUMAN_PENDING and APPROVED mappings.
11. Keep `mission_advance.py` structurally unchanged except for helper signatures. Preserve default-on pipeline and explicit-off behavior.
12. Add focused tests, import smoke, call-count tests, and normalized byte boundary tests.

## Write-race resolution
A persistence becomes the single arbiter for `clarifier_interview` replacement. It compares pending identity by source, question ids, and status. Cross-source pending replacement is blocked by default. Same-source/same-id updates may refresh metadata or prompt text without losing answers. Completion remains only in `record_clarifier_answers`, which sets `status=complete` and `completed_at`. Controlled replacements require explicit `replace=True` or equivalent internal parameter. Callers must use the returned actual persisted state, preventing SSE, HTTP, inbox harvest, and run.json divergence.

## Acceptance criteria
AC1, steps 1/5/9/11: With `AGENT_LAB_CLARIFIER_ENGINE` unset, A static question selection, B CLARIFY round advancement, and C mission-loop CLARIFY behavior are unchanged; `AGENT_LAB_PIPELINE` remains default-on and explicit 0/false disables pipeline.
AC2, steps 2/4/5/7: With `AGENT_LAB_CLARIFIER=1` and `AGENT_LAB_CLARIFIER_ENGINE=1`, A surface emits/persists C-backed questions in v2 shape, preserving C categories including `criteria` and `context`.
AC3, steps 9/10: With plan_workflow active, pipeline enabled, and engine on, B advances from CLARIFY only when `clarity_threshold_met` is true or after visible pending questions are answered and threshold becomes true; `_mirror_verified_loop_status` still maps HUMAN_PENDING to `pending_approval`.
AC4, steps 6/7/8: A persist does not clobber a pending C-created interview during a later A turn; after `record_clarifier_answers` completes it, a subsequent controlled A/C write can create the next pending interview.
AC5, steps 3/8/11: C anchor-skip still short-circuits; anchored tasks create no new persisted interview, inbox question, or SSE prompt solely due to the engine.
AC6, steps 2/3/8: Under `AGENT_LAB_MOCK_AGENTS=1`, C scoring/questions and A engine-backed interviews are deterministic and require no live agent calls.
AC7, steps 4/6/7: GET/POST `/sessions/{id}/clarifier-interview(/answers)`, public clarifier shape, snapshot `clarifier_interview`, inbox T-Q0 harvest, and `sync_clarifier_answers_from_inbox` keep the same field names and single-store behavior.
AC8, steps 9/10: `approve_plan` remains the only transition to APPROVED/running execution; clarity gating never starts execution directly.
AC9, steps 1/5/9: Flag matrix tests cover CLARIFIER on/off, CLARIFIER_ENGINE on/off, PIPELINE default-on/explicit-off, and plan_workflow active/inactive, including `CLARIFIER=0 + CLARIFIER_ENGINE=1 + PIPELINE=1`, without duplicate stores or stranded CLARIFY.
AC10, step 9: B false-threshold hold implies at least one human-visible pending Human Inbox question exists and is harvestable; if no visible question can be created, B must not silently hold and must expose deterministic notice/error.
AC11, steps 4/7: `criteria` and `context` are included in typed category contract, mypy is clean, and public-contract tests prove API/frontend consumers receive them as optional raw strings without enum breakage.
AC12, steps 6/7/8: `persist_clarifier_interview` returns actual persisted state or structured persisted result; `room_turn_flow` emits clarifier SSE prompts only from actual persisted state.
AC13, steps 2/3/5: Engine-backed A performs at most one C panel scoring pass per turn with topology off, and at most the documented one panel pass plus one topology decomposition call when topology is on.
AC14, steps 1/5/7/9/11: OFF-parity boundary tests with frozen/normalized time prove byte-stability for SSE `clarifier_prompt`, run.json `clarifier_interview`, GET/POST clarifier HTTP envelopes, runtime snapshot, T-Q0 inbox item fields, plan_workflow complete payload with no new clarity fields when engine off, and absence of any parallel store.
AC15, step 1: `AGENT_LAB_CLARIFIER_ENGINE` appears in runtime flag registry and `/api/health/flags` with default false/off.

## Verification
Focused tests:
- `tests/test_session_clarifier.py`: engine-off static parity; category Literal includes criteria/context; identity-aware persist blocks cross-source pending replacement, allows same-source/same-id update, returns actual state; `record_clarifier_answers` completion still works.
- `tests/test_clarity.py`: `lateral_questions_from_result` preserves ordering; anchor-skip creates no interview/question; mock determinism; one-pass call count with topology off/on.
- `tests/test_clarifier_engine.py`: adapter is pure, no storage writes, lazy import smoke, C categories preserved, engine flag default-off.
- `tests/test_plan_workflow.py`: false-threshold creates Human Inbox question and holds only with visible pending question; off-path keeps round-counter behavior; HUMAN_PENDING/APPROVED mirror unchanged; required flag matrix.
- `tests/test_room_turn_flow.py` or existing room flow tests: both blocks persist first and emit SSE from persisted state; blocked replacement does not emit stale candidate prompts.
- `tests/test_mission_advance.py`: pipeline default-on, explicit-off, ambiguous CLARIFY question creation, anchored DISCUSS advance.
- HTTP/snapshot/inbox contract tests: normalized byte comparisons for GET/POST clarifier envelopes, runtime snapshot, T-Q0 fields, and no plan_workflow clarity payload fields when engine off.

Commands:
1. Run focused tests above.
2. Run `make test-fast`; raise fast-bucket budget if bounded engine tests require it.
3. Run `ruff check` on changed files.
4. Run `ruff format --check` on changed files.
5. Run `mypy` on changed files or repository mypy target.

## Risks and mitigations
1. Plan-workflow deadlock: B can hold without answer path. Mitigation: Human Inbox delivery and AC10.
2. Persist desync: SSE may show non-persisted candidate questions. Mitigation: A persist returns actual state; room emits only persisted prompts; AC12.
3. Category drift: mapping C dimensions to old labels loses meaning. Mitigation: extend Literal with `criteria` and `context`; mypy and contract tests.
4. Flag matrix surprise: `CLARIFIER=0 + ENGINE=1 + PIPELINE=1` can have no A surface while B gates. Mitigation: B uses Human Inbox independent of A clarifier flag; matrix tests.
5. Pipeline default regression: treating pipeline as default-off would break current behavior. Mitigation: preserve default-on and explicit opt-out; AC1.
6. Live cost: adapter could double-score. Mitigation: one-pass helper; AC13.
7. Import cycle: A, C, adapter can cycle. Mitigation: adapter has no storage writes and lazy C imports; no top-level A/C imports except `TYPE_CHECKING`; import smoke test.
8. Inbox schema regression: B-created C questions may not match harvest assumptions. Mitigation: use existing Human Inbox question fields and T-Q0 contract tests.
9. Approval bypass: clarity-met could start execution. Mitigation: leave `_mirror_verified_loop_status` and `approve_plan` unchanged; AC8.
