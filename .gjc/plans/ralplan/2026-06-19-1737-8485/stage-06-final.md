# Final Plan (pending approval): Unify agent-lab CLARIFY Subsystems

> Consensus: Planner (stage-02) → Architect (stage-03, BLOCK→addressed) → Planner revision (stage-04) → Critic (stage-05, OKAY, 0 blocking). Run id 2026-06-19-1737-8485.

## Summary
Unify CLARIFY so that **C (`clarity.py`) is the adaptive engine**, **A (`session_clarifier.py` + its HTTP/SSE/snapshot/inbox wiring) is the single question surface and `run.json.clarifier_interview` owner**, and **B (`plan_workflow.py`) is the approval gate** that holds CLARIFY only when a human-visible pending question exists. Chosen approach: **Opt-B narrowed** — a pure lazy `clarifier_engine.py` adapter, `AGENT_LAB_CLARIFIER_ENGINE` default-off, B false-threshold questions delivered through the **Human Inbox**, identity-aware A persistence, and **one-pass** C scoring.

## Principles
1. Single store: `run.json.clarifier_interview` is the only durable interview store; no parallel C or B store.
2. Layering: A owns public shape and persistence; B owns plan-workflow gating and approval; C owns scoring, anchor-skip, topology, and adaptive questions.
3. Additive flags: engine behavior opt-in via `AGENT_LAB_CLARIFIER_ENGINE=1`; `AGENT_LAB_CLARIFIER` gates the normal A surface; `AGENT_LAB_PIPELINE` remains default-ON with explicit false/0 opt-out.
4. Visible-hold invariant: B may hold CLARIFY on unmet clarity only when at least one human-visible pending question exists.
5. Contract stability: HTTP envelopes, SSE payload shape, snapshot fields, T-Q0 inbox fields, `_mirror_verified_loop_status`, and `approve_plan` remain stable.

## Decision Drivers
1. Reachability: every false-threshold CLARIFY hold needs a visible answer and harvest path (the prior BLOCK).
2. OFF-parity: engine-off behavior must be byte-stable at public boundaries with frozen/normalized time.
3. Bounded cost and import safety: engine-backed A uses at most one C panel pass per turn; A/C/adapter imports cannot cycle.

## Options considered
- **Opt-A** (inject C at room_turn_flow A call sites): useful spike, but `plan_workflow_skips_server_clarifier` means B reachability is unsolved unless skip logic is weakened; duplicates policy across two blocks. Rejected as non-durable.
- **Opt-B narrowed** (pure adapter + Human Inbox delivery for B) — **CHOSEN**. One construction contract; solves plan_workflow reachability without weakening the skip guard; preserves A surface and B approval; testable call-count; cycle-safe via lazy imports.
- **Opt-C** (race fix only): prerequisite-sized patch; no C-backed A questions, no real clarity gate in B. Rejected as insufficient for unification.

## File-level changes
- `src/agent_lab/runtime_flags.py`: register `AGENT_LAB_CLARIFIER_ENGINE` default-off; expose via `/api/health/flags` false default.
- `src/agent_lab/session_clarifier.py`: extend `ClarifierCategory` with `criteria` and `context`; `build_clarifier_interview` consults the adapter behind the engine flag; replace unconditional `persist_clarifier_interview` with identity-aware persist that **returns actual persisted state** (or `{interview, persisted, reason}`).
- `src/agent_lab/clarifier_engine.py` (NEW): pure flag/shape adapter; no storage writes; no top-level A/C imports except `TYPE_CHECKING`; lazily imports C inside functions; one-pass question generation.
- `src/agent_lab/clarity.py`: keep `score_clarity`, `clarity_threshold_met`, anchor-skip, topology, mock behavior; add `lateral_questions_from_result(result, *, max_q=3)`; keep `lateral_questions` as a compatible wrapper (score once → helper).
- `src/agent_lab/plan_workflow.py`: in `tick_plan_workflow_after_turn` CLARIFY branch, when pipeline+engine on and `clarity_threshold_met` false, create/reference ≥1 C-backed **Human Inbox** question before holding; `_mirror_verified_loop_status` and `approve_plan` untouched.
- `src/agent_lab/room_turn_flow.py`: both server-clarifier blocks structurally intact; persist first and emit SSE **from returned persisted/public state**, never from a rejected candidate.
- `src/agent_lab/mission_advance.py`: preserve existing pipeline CLARIFY branch; adjust only for shared-helper/persist-result signatures.

## Sequencing
1. Register `AGENT_LAB_CLARIFIER_ENGINE` (default false) in `runtime_flags.py`.
2. Add pure `clarifier_engine.py`: `engine_enabled()`, `build_engine_interview(...)`, one-pass `engine_questions(...)` → `(result, questions)`; writes nothing; lazy C imports.
3. Add `clarity.lateral_questions_from_result(result, *, max_q=3)`; `lateral_questions` calls `score_clarity` once then the helper.
4. Extend `ClarifierCategory` with `criteria`, `context` (engine-off static output unchanged).
5. `build_clarifier_interview`: after `clarifier_enabled()` + text checks, call adapter when engine on; return A v2 dict with C categories preserved; else fall through to existing static branches.
6. Identity-aware `persist_clarifier_interview`: return actual persisted state; block cross-source pending replacement; allow same-source/same-id metadata updates; completion stays only in `record_clarifier_answers`; explicit `replace=True` for controlled cases.
7. `room_turn_flow.py` both blocks: build → persist → derive prompts/SSE from returned persisted state; blocked replacement omits stale candidate SSE.
8. `clarity.ensure_clarify_questions`: keep early non-complete return; use shared shape; use A's returned persisted state; preserve anchor-skip + idempotency.
9. `plan_workflow.tick_plan_workflow_after_turn`: pending inbox → keep current hold; else if pipeline+engine and threshold false → one-pass C questions → create Human Inbox question(s) using existing question fields → hold CLARIFY only after confirming ≥1 pending visible inbox question; engine-off/pipeline-off → current round-counter behavior.
10. Leave `_mirror_verified_loop_status` and `approve_plan` unchanged; add regression tests for HUMAN_PENDING/APPROVED mappings.
11. `mission_advance.py` structurally unchanged except helper signatures; preserve default-on pipeline + explicit-off.
12. Add focused tests, import smoke, call-count tests, normalized byte boundary tests.

## Write-race resolution
A persistence becomes the single arbiter for `clarifier_interview` replacement. It compares pending identity by source, question ids, and status: cross-source pending replacement blocked by default; same-source/same-id updates may refresh metadata/prompt text without losing answers; completion remains only in `record_clarifier_answers` (`status=complete`, `completed_at`); controlled replacement requires explicit `replace=True`. Callers MUST use the returned actual persisted state, preventing SSE/HTTP/inbox/run.json divergence.

## Acceptance criteria (AC1–AC15)
- **AC1** (1/5/9/11): engine unset → A static selection, B round advancement, C mission-loop CLARIFY unchanged; `AGENT_LAB_PIPELINE` default-on, explicit 0/false disables.
- **AC2** (2/4/5/7): CLARIFIER=1 + ENGINE=1 → A emits/persists C-backed v2 questions preserving `criteria`/`context`.
- **AC3** (9/10): plan_workflow active + pipeline + engine → B advances from CLARIFY only when threshold true or after visible questions answered; HUMAN_PENDING→`pending_approval` mapping intact.
- **AC4** (6/7/8): A persist does not clobber a pending C interview; after completion a controlled write can create the next pending interview.
- **AC5** (3/8/11): anchor-skip short-circuits; anchored tasks create no new interview/inbox question/SSE prompt due solely to the engine.
- **AC6** (2/3/8): under `AGENT_LAB_MOCK_AGENTS=1`, C scoring/questions and A engine-backed interviews are deterministic, no live calls.
- **AC7** (4/6/7): HTTP GET/POST clarifier endpoints, public shape, snapshot `clarifier_interview`, T-Q0 harvest, `sync_clarifier_answers_from_inbox` keep field names + single store.
- **AC8** (9/10): `approve_plan` remains the only transition to APPROVED/running; clarity gating never starts execution.
- **AC9** (1/5/9): flag matrix covers CLARIFIER on/off × ENGINE on/off × PIPELINE default-on/explicit-off × plan_workflow active/inactive, incl. `CLARIFIER=0 + ENGINE=1 + PIPELINE=1`, no duplicate stores, no stranded CLARIFY.
- **AC10** (9): B false-threshold hold implies ≥1 human-visible pending Human Inbox question (harvestable); if none can be created, B must not silently hold — deterministic notice/error.
- **AC11** (4/7): `criteria`/`context` typed, mypy clean, public-contract tests prove consumers receive them as optional raw strings (no enum break).
- **AC12** (6/7/8): `persist_clarifier_interview` returns actual persisted state; `room_turn_flow` emits SSE prompts only from persisted state.
- **AC13** (2/3/5): engine-backed A does ≤1 C panel pass per turn (topology off); ≤1 panel + 1 topology decomposition call when topology on.
- **AC14** (1/5/7/9/11): OFF-parity boundary tests (frozen/normalized time) prove byte-stability for SSE `clarifier_prompt`, run.json `clarifier_interview`, GET/POST clarifier envelopes, runtime snapshot, T-Q0 inbox fields, plan_workflow complete payload (no new clarity fields engine-off), and absence of parallel store.
- **AC15** (1): `AGENT_LAB_CLARIFIER_ENGINE` in flag registry + `/api/health/flags` default false/off.

## Verification
Focused tests: `tests/test_session_clarifier.py`, `tests/test_clarity.py`, `tests/test_clarifier_engine.py` (new), `tests/test_plan_workflow.py`, `tests/test_room_turn_flow.py` (or existing room flow test), `tests/test_mission_advance.py`, plus HTTP/snapshot/inbox contract tests (normalized byte comparisons).
Commands: (1) focused tests → (2) `make test-fast` (raise fast-bucket budget if bounded engine tests require) → (3) `ruff check` changed files → (4) `ruff format --check` changed files → (5) `mypy` changed files / repo target.

## Risks & mitigations
1. Plan-workflow deadlock → Human Inbox delivery + AC10.
2. Persist desync → A persist returns actual state; room emits only persisted prompts; AC12.
3. Category drift → extend Literal with `criteria`/`context`; mypy + contract tests.
4. Flag-matrix surprise (`CLARIFIER=0 + ENGINE=1 + PIPELINE=1`) → B uses Human Inbox independent of A clarifier flag; matrix tests.
5. Pipeline default regression → preserve default-on + explicit opt-out; AC1.
6. Live cost → one-pass helper; AC13.
7. Import cycle → adapter no storage writes + lazy C imports + TYPE_CHECKING-only top-level; import smoke test.
8. Inbox schema regression → reuse existing Human Inbox question fields + T-Q0 contract tests.
9. Approval bypass → `_mirror_verified_loop_status` + `approve_plan` unchanged; AC8.

## ADR
- **Decision**: Unify CLARIFY via Opt-B narrowed — a pure lazy `clarifier_engine.py` adapter making C the question engine behind A's surface/store, with B gating on `clarity_threshold_met` and delivering false-threshold questions through the Human Inbox. Flag-gated by `AGENT_LAB_CLARIFIER_ENGINE` (default off).
- **Drivers**: plan-workflow reachability (no silent CLARIFY deadlock), OFF-parity byte-stability, bounded live cost + import safety.
- **Alternatives considered**: Opt-A (call-site injection — leaves B unreachable under plan mode); Opt-C (race fix only — not a unification). Both rejected with rationale above.
- **Why chosen**: Opt-B narrowed is the only option that honors A=surface/B=gate/C=engine while keeping `plan_workflow_skips_server_clarifier` intact and giving plan-mode CLARIFY a reachable, harvestable answer path (Human Inbox) — closing the Architect's BLOCKING finding without weakening the approval spine.
- **Consequences**: one new small module; A's persist gains identity-aware return semantics (callers must use returned state); `ClarifierCategory` Literal expands additively; B's CLARIFY branch gains a pipeline+engine-gated clarity check with inbox delivery. All behind a default-off flag with full OFF-parity.
- **Follow-ups**: after green tests + OFF-parity proof, optionally dogfood with `AGENT_LAB_CLARIFIER_ENGINE=1`; consider later promoting C's facts (`format_facts_block`) into the plan-workflow DRAFT context; revisit whether the static A templates can be retired once the engine path is validated in live use.

## Status: PENDING APPROVAL
No product code mutated. Execution (via `/skill:ultragoal`) begins only after explicit user approval.
