# Architect Review — ultragoal G002: anti-drift A (state-externalization re-injection)

> NOTE: role-agent subagent dispatch down (architect spawn failed sub-second repeatedly). Conducted INLINE by the ultragoal leader, source-verified. Disclosed.

## Verdict
- architectureStatus: CLEAR
- productStatus: CLEAR
- codeStatus: CLEAR
- recommendation: APPROVE
- blocking count: 0

## Scope reviewed
src/agent_lab/turn_modes.py (antidrift_enabled), src/agent_lab/runtime_flags.py (AGENT_LAB_ANTIDRIFT), .env.example, src/agent_lab/context_bundle.py (_format_decision_ledger, _format_grounding_block, both injection sites), tests/test_antidrift.py.

## Findings (against constraints)
1. CORRECT SITE: confirmed established facts are injected at exactly two context-bundle constraint sites (build_slim_consensus_bundle and build_context_bundle); both now route through _format_grounding_block(run_meta, consensus_mode=...). consensus_mode is in scope at both. No new parallel context layer. OK.
2. NO DUPLICATION: the grounding helper REPLACES the prior plain _format_clarity_facts injection rather than adding a second facts block. On a panel turn with the flag on it emits one re-grounding block (re-anchor header + facts + decision ledger); off/solo it emits exactly the prior plain facts block. OK (ai-slop-cleaner: duplication avoided by construction).
3. OFF-PARITY: _format_grounding_block returns _format_clarity_facts(run_meta) verbatim unless (consensus_mode AND antidrift_enabled()); the injection-site code shape is unchanged (.strip() guard identical). With AGENT_LAB_ANTIDRIFT unset the constraints string is byte-identical. Verified by test_antidrift_off_is_plain_facts (== assertion, frozen — facts/ledger blocks contain no timestamps) and the full fast lane staying green (1519 passed). OK (AC6).
4. PANEL RE-INJECTION (AC7): on flag-on panel turns the block re-injects facts + the recent decision ledger (run.json goal_ledger, capped, garbage-tolerant). Solo turns get the light plain-facts block. OK.
5. REUSE: format_facts_block / established_facts reused via _format_clarity_facts; no parallel facts store. The ledger reads the existing run.json goal_ledger. OK.
6. SHARED FLAG: antidrift_enabled lives in turn_modes (low-level, no cycle) so G003 (room_consensus_rounds / plan_workflow) can reuse it. OK.
7. SPINE / ROUTING UNTOUCHED: no changes to plan_workflow approval spine, verified_loop, or the G001 routing lever. Additive only. OK.

## Code-side notes (non-blocking)
- _format_decision_ledger is defensive (non-dict run, non-list ledger, missing event field, mixed garbage entries) and capped via max_entries.
- Coverage: AC6 (OFF-parity both consensus modes + empty), AC7 (panel re-injection with/without ledger, solo light, empty-state empty), ledger rendering/cap/garbage, flag spellings.

## Verification observed (leader-run, real)
- ruff check + format --check: clean.
- mypy ratchet: 243/243 (G002 delta 0).
- make test-fast: 1519 passed, 1 skipped, 0 failed.
- focused: 38 passed (artifacts/g002-antidrift-qa.txt).
