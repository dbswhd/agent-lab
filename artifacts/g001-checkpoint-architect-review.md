# Architect Review — ultragoal G001: P0 Checkpoint/Resume Layer

> NOTE: role-agent subagent dispatch down all session. Conducted INLINE by the ultragoal leader, source-verified. Disclosed.

## Verdict
- architectureStatus: CLEAR
- productStatus: CLEAR
- codeStatus: CLEAR
- recommendation: APPROVE
- blocking count: 0

## Scope reviewed
src/agent_lab/checkpoint_store.py (new), src/agent_lab/run_meta.py (patch_run_meta hook), src/agent_lab/runtime_flags.py (AGENT_LAB_CHECKPOINT), .env.example, tests/test_checkpoint_store.py, tests/test_integration_registry.py (budget).

## Findings (against plan + constraints)
1. CORRECT LEVER: capture is the single chokepoint inside patch_run_meta. Prior phase signature is captured from the read `run` BEFORE `updater` (handling in-place mutation), compared to `_phase_signature(updated)` after the write; append only on change. Matches the consensus plan exactly. CLEAR.
2. OFF-PARITY (PRIMARY): the hook is behind `if os.getenv("AGENT_LAB_CHECKPOINT") ... in {1,true,yes,on}`. Flag off => no checkpoint_store import, no prior-signature read, no append. test_ac5_off_parity_run_json_byte_identical proves run.json bytes are identical flag-off vs flag-on; full default-off suite (1555 passed) unchanged. CLEAR.
3. SCOPE: snapshot is strictly CHECKPOINT_FSM_KEYS (mission_loop/plan_workflow/verified_loop/goal_ledger/token_budget/cost_ledger/budget_status/budget_exhausted); AC7 asserts no chat/plan/artifact keys leak. CLEAR.
4. RESUME = restore-then-stop: resume_from_checkpoint restores the FSM subset via write_run_meta and returns; no FSM tick/dispatch (AC4). Because the capture hook lives only in patch_run_meta, the write_run_meta restore self-suppresses any new checkpoint (AC11). CLEAR.
5. COVERAGE (Architect HIGH from ralplan, AC10): plan_workflow.set_plan_workflow_phase routes through patch_run_meta (source guard test) and a behavioral test drives a real plan_workflow PEER_REVIEW transition and asserts exactly one checkpoint — so the chokepoint covers FSM transitions; no direct write_run_meta phase bypass. CLEAR.
6. RETENTION: cap 200 drop-oldest mirroring goal_ledger; AC6 asserts cap + monotonic n + oldest dropped. CLEAR.
7. INDEPENDENCE/IMPORT LANE: checkpoint_store is pure stdlib; AC8 source test asserts no room/mission_loop/plan_execute/runtime imports; crash_recovery untouched (its tests green). run_meta lazy-imports checkpoint_store only inside the flag guard. CLEAR.
8. NO SQLITE / NO TIME-TRAVEL / NO BOOT-AUTO-RESUME: append-only JSONL, manual resume only, deferred items absent. CLEAR.

## Verification observed (leader-run, real)
- ruff check + format --check: clean.
- mypy ratchet: 243/243 (delta 0).
- make test-fast: 1555 passed, 1 skipped, 0 failed (clean rerun; an earlier run showed a known load/timing flake in tests/test_partial_retry.py real-mock-agent retries, unrelated to this OFF-by-default change — passes isolated + on rerun).
- focused: 37 passed (artifacts/g001-checkpoint-qa.txt) covering AC1-AC11 + Critic N1 (behavioral plan_workflow transition captured) + N2 (snapshot keys ⊆ CHECKPOINT_FSM_KEYS).
