# FINAL PLAN (pending approval) — agent-lab Room comms token compaction

Run `2026-06-19-1737-8485` · deliberate · consensus folded: Planner -> Architect (WATCH / REQUEST CHANGES, 3 blockers) -> Critic (ITERATE, 7 deltas), all resolved below. **Status: PENDING APPROVAL — no source edits, no execution. Recommended execution: ultragoal.**

## Objective
Reduce Room consensus/context token cost (biggest sink: re-sent recent transcript + always-pinned current-turn msgs; quadratic same-turn reply replay) WITHOUT changing chat.jsonl as durable SSOT or consensus correctness. Three changes, additive + flag-gated behind AGENT_LAB_COMMS_COMPACT (except unconditional §4-5 bugfixes).

## Consensus claim verification (architect, exact lines CONFIRMED)
- Bug A: writer key "guidance" at context_bundle.py:328 AND :701; reader "guidance_block" at reply_policy.py:223 (-> communicate_kpis guidance_chars always 0).
- Bug B: writer entry["usd"] at cost_ledger.py:139; reader "cost_usd" at usage_monitor.py:62 (-> provider_spent_usd always 0.0).
- turn_state additive: render appends full recent + full peer after turn_state at context_bundle.py:141-156.
- Quadratic: working = messages + all_replies rebuilt at room_consensus_rounds.py:161,174,209,330,410; endorse-loop thread rebuild :497.
- Always-pinned current turn: room_context.py:478-484 pinned_current_turn_messages; efficiency-only cap at :508-512.
- Seams: collect_peer_messages :514-538, format_peer_block :560-568, dedupe_peer_from_recent :542-557, consensus_follow_up room_consensus.py:160-190.

## ADR
Additive + flag-gated (AGENT_LAB_COMMS_COMPACT; default OFF until stabilized, default-on per AC5). Reuse trim/efficiency infra. chat.jsonl stays SSOT; only prompt SHAPE changes. §4-5 bugfixes unconditional. Alternatives B (rewrite) and C (efficiency-only) rejected (blast radius / leaves default path unfixed).

## Resolved blockers (architect REQUEST CHANGES)
- B1 slim bundle efficiency-gated: build_slim_consensus_bundle gated on slim_context AND efficiency_mode (context_bundle.py:251-252). FIX: relax so AGENT_LAB_COMMS_COMPACT enters the slim path independently of efficiency_mode (OR-condition / dedicated branch). OFF-parity: flag unset + efficiency off => byte-identical.
- B2 L{n} fallback not wired: dedupe_peer_from_recent (:542-557) strips peer prose from the recent block, so digest refs would point to ABSENT lines. FIX (design): in compact mode, retain the immediately-relevant round's peer FULL prose in the numbered recent thread (L-addressable, NOT deduped); older same-turn rounds collapse to digest-only excerpts (no L promise). Token win = dropping older-round full prose; L{n} valid for retained round. Ref-integrity test required.
- B3 cost-key bookkeeping: cost_ledger writes "usd" across cumulative bookkeeping (_recompute_cumulative, _empty_agent_entry, budget_status, session_budget_action, quality_judge._cumulative_usd). FIX DIRECTION: change the READER usage_monitor.py:62 to read "usd" (match writer + all consumers; NO writer/cumulative churn). Guidance FIX DIRECTION: change the WRITER (context_bundle.py:328 & :701 AND build_slim_consensus_bundle) to record "guidance_block" (match KPI/reply_policy reader). Update tests test_cost_ledger.py:69-70, test_dynamic_account_chain.py:48.
- Peer header load-bearing: keep '[이번 턴 · 동료 발화]' header EXACTLY (room_chat_channels.py:24-40 PEER_HEADER_ECHO) or update regex; add human-visibility parity test.
- Divergence: scope AGENT_LAB_COMMS_COMPACT OUT of divergence mode (divergence.py / turn_modes _is_divergence) — compact excerpts break approach-distinct option extraction.
- G002 pin algo: NEW helper keeping latest Human + latest reply per agent + compact envelopes (NOT newest-N cap_pinned_messages :444-472). Append L-ref note to the RENDERED recent-block STRING, never to the message list (avoid format_thread_numbered_slice corruption :615-637).

## Resolved critic deltas (ITERATE 1-7)
1. OFF-parity test contract per flagged story: test_off_parity_<story> asserts build_context_bundle(...).render() byte-identical with flag unset.
2. AC2 rig: synthetic 3 agents × 4 rounds × ~4K-char replies; measure len(format_peer_block(collect_peer_messages(msgs, agent, parallel_round=2))) before/after; reduction = 1 - new/old; artifact tests/fixtures/comms-compaction-benchmark.json.
3. Compact-envelope schema: "L{round} {AGENT} {act}: {<=140-char excerpt} [refs: L{n},...] [art: id,...]"; missing act -> "SAY"; missing refs/art -> omit field.
4. L{n} surfacing: numbered-thread header + explicit prompt note 'full prose at chat.jsonl L{n}'; ref-integrity test asserts every digest ref resolves to a present numbered line.
5. Bugfix key-direction pinned (see B3): guidance writer -> guidance_block; cost reader -> usd.
6. AC3 harness: AGENT_LAB_MOCK_AGENTS=1 + patched call_agent_reply (or AGENT_LAB_MOCK_STRUCTURED_ENVELOPE) emitting ENDORSE envelopes; 3-agent fixture; assert consensus reaches endorsed with compaction ON.
7. Risks expanded: L{n} ref drift; efficiency-mode/artifact-only interaction; mock-realism gap; default-ON migration criteria (AC5).

## Stories (ultragoal goals; ordered)
- G001 §4-5 bugfixes (UNCONDITIONAL): guidance writer -> "guidance_block" (context_bundle :328,:701 + slim bundle); usage_monitor reader -> "usd"; update affected tests; regression asserts guidance_chars_total>0 and provider_spent_usd>0.
- G002 §4-2 pin char cap (flag-gated): per-agent-latest pin helper; string-level L-ref note; char cap outside efficiency mode; OFF-parity named test.
- G003 §4-1 blackboard+delta peer block (flag-gated): relax slim-bundle gate (B1); compact peer digest + retained-round full prose (B2); header preserved; divergence scoped out; OFF-parity + ref-integrity + human-visibility tests.

## Acceptance criteria
- AC1 OFF-parity byte-stable (named test per story); make test-fast at baseline.
- AC2 >=40% R2+ peer-payload char reduction via the rig; artifact committed.
- AC3 consensus reaches endorse threshold (floor=2) with compaction ON (mock harness).
- AC4 guidance_chars_total>0 and provider_spent_usd>0 (regression).
- AC5 flag-removal milestone recorded post-stabilization.
- AC6 human-visibility parity (peer header) + divergence option count unaffected (named tests).

## Sequencing
G001 -> G002 -> G003 (metrics first, then kill quadratic, then behavioral peer compaction). No dependency inversion.

## Risks / pre-mortem
R1 OFF-parity regression -> flag-gate + named OFF-parity tests. R2 delta peer block stops consensus -> AC3 harness + retained-round prose + L{n}. R3 pin cap drops needed context -> per-agent-latest retention. R4 dual-path debt -> AC5. R5 L{n} ref drift -> string-level note + ref-integrity test. R6 divergence/efficiency interaction -> scoped-out + parity tests. R7 mock-realism gap -> documented; live spot-check deferred.

## Out of scope
External memory/context server; §4-3 role/route context modes; §4-4 KV-cache prefix ordering; §4-6; broad context redesign.

## Status: PENDING APPROVAL — execution requires explicit user approval; then run via ultragoal (G001 -> G002 -> G003) under the hardened completion gate.
