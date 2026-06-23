## Summary
The CLARIFY unification mostly follows the A surface/store, B gate, C engine layering and the prior plan_workflow silent-deadlock blocker is closed in the normal path: B only holds when has_pending_question is true, and no-question/no-visible paths return deterministic clarity_notice values and advance to DRAFT. I cannot approve because the identity-aware persistence contract is weaker than the approved same-source/same-id design, and plan_workflow ignores the persistence arbiter before harvesting Human Inbox questions.

## Analysis
- Adapter purity is good: src/agent_lab/clarifier_engine.py imports neither A nor C at top level, does not reference patch_run_meta, and lazily imports score_clarity and lateral_questions_from_result inside engine_questions.
- C one-pass helper exists: clarity.py adds lateral_questions_from_result and engine_questions uses score_clarity once before deriving questions. Anchor skip and mock scoring remain in score_clarity.
- A gate remains behind AGENT_LAB_CLARIFIER, and engine is additionally behind AGENT_LAB_CLARIFIER_ENGINE. Engine-off build falls through to static templates, and engine-off persistence remains unconditional overwrite.
- Room SSE in the folder-backed paths renders from persisted.get('interview'), so rejected candidates are not emitted in those paths.
- B gate is active only when engine_enabled and pipeline_enabled are both true. With unmet clarity it harvests T-Q0 questions and verifies has_pending_question before returning wait_inbox; no-question and no-visible-question paths return clarity_notice and then tick advances DRAFT.
- Approval spine is intact: _mirror_verified_loop_status only maps CLARIFY and DRAFT-like phases to proposing, HUMAN_PENDING to pending_approval, and only _finalize_plan_approval writes phase APPROVED and running.
- Tests/test_clarifier_engine.py covers registry default off, adapter purity/import smoke, anchor skip/mock questions/one-pass engine_questions, engine-backed build, engine-off static, cross-source block, engine-off overwrite, visible inbox hold, clarity-met advance, approval non-bypass, and CLARIFIER-off B reachability.
- Test sufficiency gap: the main AC suite does not cover same-source different-id pending replacement, does not explicitly cover AGENT_LAB_PIPELINE=0, and does not include the no-visible fallback; an unlisted redteam test covers no-visible, but the identity gap remains untested.

## Root Cause
The implementation treats source equality as interview identity and lets plan_workflow proceed from candidate prompts even when A's persistence layer may have rejected that candidate. That weakens the single-store arbiter from source plus question identity to source only, and lets B create visible questions that are not necessarily the persisted clarifier_interview.

## Findings
1. HIGH - src/agent_lab/session_clarifier.py:284-285 - Same-source pending replacement is allowed solely by source equality. The approved design says same-source/same-id updates only; this code allows a new clarity_engine interview with different question ids to overwrite an existing pending clarity_engine interview, losing answers or stranding old Human Inbox items. Fix by comparing stable pending question ids before same_source_update, merging only same-id metadata or requiring replace=True for different ids while preserving existing answers.
2. HIGH - src/agent_lab/plan_workflow.py:606-609 - _clarity_gate_questions ignores persist_clarifier_interview's returned actual state and harvests the candidate prompts. If persistence is blocked by an existing cross-source pending interview, B can hold or ask a T-Q0 Human Inbox question that is not the single run.json clarifier_interview, so answer harvest and public clarifier state can diverge. Fix by using the returned persisted interview for prompts, or by treating rejected persistence as no visible persisted question and advancing with a deterministic notice.
3. MEDIUM - tests/test_clarifier_engine.py - The main AC1-AC15 suite does not exercise same-source different-id pending replacement and does not directly exercise AGENT_LAB_PIPELINE=0. Add regression tests for both; keep the no-visible fallback test in the main AC suite or ensure the redteam test is included in required fast verification.
4. LOW - src/agent_lab/room_turn_flow.py:639-646 - Direct run_room calls without a pre-created folder still emit a clarifier_prompt from the candidate because there is no folder to persist into yet. API-created sessions are folder-backed, so this is not the primary product path, but direct public callers can miss run.json clarifier_interview durability. Consider bootstrapping a folder before clarifier emission when clarifier_questions are produced.

## Recommendations
1. Enforce same-source plus same-id identity in _persist_decision and preserve pending answers during allowed metadata refreshes.
2. In plan_workflow, capture persist_clarifier_interview's return and derive Human Inbox prompts from the actual persisted interview; if the candidate was rejected and no persisted interview questions are harvestable, advance with clarity_no_visible_question rather than holding.
3. Add focused tests for same-source different-id rejection, pipeline explicit off, and plan_workflow rejected-persist behavior.
4. Optionally promote the no-visible fallback regression into tests/test_clarifier_engine.py so AC10 coverage is visible in the main acceptance suite.

## Architectural Status
BLOCK

## Code Review Recommendation
REQUEST CHANGES

## Trade-offs
- Strict same-id matching: preserves answers and the single-store invariant; requires explicit replace for new rounds.
- Source-only matching: simpler and currently implemented; risks silent clobbering of pending interviews.
- B using actual persisted prompts: slightly more plumbing; keeps Human Inbox, public API, and run.json aligned.
- B using candidate prompts: simpler; can create a durable Human Inbox question outside the accepted interview.
