# Plan Revision (stage_n 2) — Dynamic Resilient Multi-Agent Room

Folds Architect (WATCH) + Critic (ITERATE) feedback into the Planner plan. Deltas only; all other sections of stage-01-planner stand.

## DELTA 1 — Capability honesty: proactive = LOCAL budget heuristic (P3)
Phase 2 reframed. `usage_monitor.should_preempt` does NOT claim server-side remaining quota. It triggers on either:
- a **local budget cap** computed from cost_ledger cumulative spend/tokens for the account (an agent-lab-local estimate), OR
- **provider usage headers** when the API actually returns them (KIMI/cursor-API responses).
Wording everywhere changed from "proactive usage/token threshold (knows remaining quota)" to "local budget cap / usage-header heuristic." OAuth/CLI providers are reactive-only (cannot expose usage). Acceptance criterion #7 reworded: "proactive preemption fires for usage-exposing providers when the LOCAL budget/usage-header heuristic crosses threshold; OAuth/CLI never preempt, only reactive failover."

## DELTA 2 — auth_kind-branched account semantics (OAuth N-account corrected)
`provider_registry.auth_kind` drives account handling:
- **api / local** (KIMI, cursor-API, local): full secret-string N-account chain in `account_chain.get_account_chain` — sequential rotation in-turn on credential/quota failure, cooldown per account.
- **oauth / cli** (claude, codex): exactly ONE active CLI OAuth profile at a time (process-global). accounts[] for these stores **profile references/labels, not secrets**. In-turn behavior = single active profile; on credential failure the chain does NOT rotate keys — it advances to the **next seat/provider** (roster substitution) and may schedule a **between-turn profile switch** (re-login to a spare profile) as a best-effort, never an in-turn racy swap.
- Acceptance criterion #1 split:
  - #1a (api/local): account 1 quota error -> in-turn switch to account 2 -> 3...
  - #1b (oauth/cli): account 1 (profile) failure -> NO in-turn key rotation; seat substitution to next provider; spare profile becomes active only on a subsequent turn.
- account_chain unit tests assert the correct branch per auth_kind; oauth tests assert NO fictional in-turn key rotation.

## DELTA 3 — Seat identity vs agent identity (explicit)
`agent_roster.select_roster()` returns concrete live agent ids for the turn. consensus_gate `allocate_roles`/`effective_consensus`, role allocation, run.json observability, and `/agents` all operate on the **live roster ids**, never the static ["cursor","codex","claude"]. When a substitute fills a seat, it participates under its own id and is counted in consensus as itself.

## DELTA 4 — Explicit OFF-parity acceptance test (new criterion #10)
- [ ] **OFF-parity**: with AGENT_LAB_DYNAMIC_ROOM unset, `room.run_room` selects exactly ["cursor","codex","claude"] and consensus_gate behavior is byte-stable vs current; a named test asserts the static path is unchanged. (Mirrors the AGENT_LAB_PIPELINE OFF-parity pattern already in the repo.)

## Updated Acceptance Criteria (mock, AGENT_LAB_MOCK_AGENTS=1)
1a. api/local N-account in-turn failover; 1b. oauth/cli single-profile + seat-substitution failover (no in-turn key rotation);
2. model-exhaustion -> seat substitution (KIMI->local);
3. 3->2 consensus floor; 4. 2->1 solo;
5. cooldown retry (gated on is_credential_failure only);
6. slash 6 commands;
7. proactive preemption = local budget/usage-header heuristic for usage-exposing providers only; OAuth/CLI reactive only;
8. local fallback guarantees >=1 agent;
9. make test-fast green == baseline+new;
10. OFF-parity named test (AGENT_LAB_DYNAMIC_ROOM unset == current behavior).

## Updated ADR follow-ups
- proactive threshold numeric default (local budget cap value);
- local fallback model/endpoint default;
- OAuth spare-profile between-turn switch mechanics (best-effort, deferred);
- collapse dual credential representation post-dogfooding;
- dynamic-room flag default-on after dogfooding (mirrors AGENT_LAB_PIPELINE milestone).

## Principle check (post-revision)
P3 capability honesty: now UPHELD (proactive explicitly local-heuristic). All others remain upheld.
