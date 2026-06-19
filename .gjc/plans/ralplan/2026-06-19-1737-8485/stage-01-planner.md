# RALPLAN Stage 01 — Planner: agent-lab Room comms token compaction

Run `2026-06-19-comms-token-compaction` · deliberate · recommended execution: ultragoal. **Planning only — no source edits; pending approval.**

## Objective
Reduce Room consensus/context token cost without changing `chat.jsonl` as durable SSOT or consensus correctness, via three changes from the architect review (§4-5 bugfixes, §4-2 pin char cap, §4-1 blackboard+delta peer block).

## Evidence (architect review: .gjc/plans/ralplan/2026-06-18-dynamic-resilient-room/stage-03-architect.md)
- `turn_state` compact blackboard exists (room_turn_state.py) but `ContextBundle.render` (context_bundle.py:140-154) appends full recent prose + full peer prose anyway -> additive, not substitutive.
- Sink: recent transcript + always-pinned current-turn msgs re-sent per agent per round; consensus deep/critical up to 30 calls x 96K chars ~= 720K input tokens/turn (context_limits.py recent=8/96000; room_consensus.py 12 rounds/30 calls).
- Quadratic replay: run_consensus_agent_rounds rebuilds working = messages + all_replies each call (room_consensus_rounds.py ~128-209,501-534) -> ~217K-543K tokens of re-sent same-turn replies.
- Bug A: context_bundle.py:701 writes layer key "guidance"; reply_policy.py:219-223 / communicate_kpis.py read "guidance_block" -> guidance overhead underreported.
- Bug B: cost_ledger.py:134-139 writes entry["usd"]; usage_monitor.provider_spent_usd ~49-63 reads "cost_usd" -> local budget preemption inert.

## ADR
- Decision: Additive + flag-gated behavioral changes behind one env flag (AGENT_LAB_COMMS_COMPACT, default OFF until stabilized, then default-on per AC5). Reuse existing trim/efficiency infra (room_context.py helpers, context_limits.py, efficiency_limits). chat.jsonl stays SSOT; only prompt SHAPE changes; full prose stays addressable via chat.jsonl L{n} refs (format_thread_numbered_slice exists). 4-5 bugfixes are UNCONDITIONAL (pure correctness, no flag).
- Alternatives: (B) rewrite context assembly - rejected: blast radius on load-bearing consensus path, OFF-parity loss. (C) enable compaction only in efficiency mode - rejected: leaves default path (the actual pain) unfixed.
- Consequences: temporary OFF/ON dual path -> AC5 flag-removal milestone prevents permanent debt.

## Stories (proposed ultragoal goals; ordered by ROI/risk)
- G001 — 4-5 key-mismatch bugfixes (unconditional). Align guidance/guidance_block key and usd/cost_usd key; add regression tests. Cheap; unblocks token/spend measurement used by G002/G003.
- G002 — 4-2 current-turn pin char cap (flag-gated). Cap pinned current-turn chars outside efficiency mode in pinned_current_turn_messages / trim_messages_by_chars_pinned / prepare_recent_messages; always keep latest Human + latest reply per agent + compact envelopes; older same-turn prose -> L{n} refs. Eliminates quadratic growth.
- G003 — 4-1 blackboard+delta peer block (flag-gated). collect_peer_messages/format_peer_block (room_context.py ~514-570) emit {agent, round, act, refs, 1-2 line excerpt, artifact ids}; run_consensus_agent_rounds uses slim consensus_follow_up (anchor+delta) as primary input; full prose via L{n}. Biggest win, highest behavioral risk -> last.

## Test spec (mock-only, AGENT_LAB_MOCK_AGENTS=1)
- OFF-parity named test per flagged story: flag unset => byte-stable comms payload vs current.
- Unit: bug A -> communicate_kpis guidance_chars_total > 0; bug B -> provider_spent_usd returns recorded spend; pin char-cap math; delta peer formatting + L{n} ref integrity.
- Mock integration: synthetic high-history consensus turn still reaches endorse threshold (floor=2) with compaction ON; before/after token-char artifact, target >=40% R2+ peer-payload reduction.
- Gate per goal: make test-fast green at baseline+new, ruff clean, mypy no new errors.

## Role roster
- executor: bounded implementation per story.
- architect: post-integration read-only review (architecture/product/code).
- critic: pre-execution plan critique.

## Risks / pre-mortem
- R1 OFF-parity regression -> flag-gated + named OFF-parity test as hard gate.
- R2 delta peer block stops consensus reaching -> AC3 mock integration; preserve endorse threshold/anchor/AMEND; L{n} full-prose fallback.
- R3 pin cap drops needed current-turn context -> always keep latest Human + latest reply per agent; cap only older same-turn prose.
- R4 dual-path debt -> AC5 flag-removal milestone after ON stabilization.

## Acceptance criteria
- AC1 OFF-parity byte-stable when flag off; make test-fast at baseline.
- AC2 >=40% R2+ peer-payload char reduction in mock high-history consensus turn (before/after artifact).
- AC3 consensus still reaches endorse threshold with delta peer block; anchor/AMEND/L{n} preserved.
- AC4 guidance_chars_total>0 and provider_spent_usd>0 with regression tests.
- AC5 flag-removal milestone recorded for post-stabilization.
