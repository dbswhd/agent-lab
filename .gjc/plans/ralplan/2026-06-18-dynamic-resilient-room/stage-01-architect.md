# Architect Review (stage_n 1) — Dynamic Resilient Multi-Agent Room

## Status: WATCH
## Recommendation: COMMENT (fold required refinements before final)

## Steelman of the plan
The additive, flag-gated Option 1 is the right shape: it reuses credential_store/consensus_gate/room, preserves OFF-parity, and is reversible — consistent with the repo's proven flag-gated pattern. Leaf-module decomposition (provider_registry/account_chain/usage_monitor/agent_roster/slash_commands) keeps each behavior independently mock-testable. The local-fallback-as-floor is the correct mechanism to guarantee the spec's "never 0 agents" invariant. Pre-mortem scenarios 2 and 3 (cooldown stranding, consensus mis-set) are the real failure modes and are mitigated concretely.

## Antithesis / Tradeoff tensions (must resolve)
1. **OAuth multi-account is not a secret chain (CRITICAL).** claude/codex are OAUTH_ONLY; `get_credential_chain` returns [] today because auth is CLI OAuth, not key strings. "N-account" for these providers means multiple CLI OAuth *profiles*, and the CLI's active profile is process-global — you cannot have codex-account-1 and codex-account-2 both live in the same turn without serialized profile switching (slow, racy). The plan's accounts[] secret model only fits api/local providers (KIMI/cursor-API/local). REQUIRED: Phase 1/2 must branch by `auth_kind` — api/local => secret-string N-account chain; oauth/cli => one active profile + reactive failover to the *next provider/seat* (or a between-turn profile re-login), NOT in-turn secret rotation. State this explicitly so the implementer does not attempt impossible in-turn OAuth key rotation.

2. **"Proactive threshold" via cost_ledger is a LOCAL budget heuristic, not server quota (CRITICAL).** cost_ledger tracks agent-lab's own cost estimate; it does not know the provider's server-side remaining quota. So proactive preemption is really "local budget cap reached" (or provider usage headers when present), not "provider says you're almost out." REQUIRED: reframe Phase 2 proactive as a local budget/usage-header heuristic; do not promise true remaining-quota knowledge. This keeps the capability-honesty principle intact.

3. **Seat identity vs agent identity.** When KIMI substitutes into an empty seat, downstream (consensus_gate, run.json, /agents) must count the *actual participating agent ids*, not the fixed default names. The plan implies this via select_roster returning concrete ids — make it explicit that consensus and role allocation operate on the live roster ids, never the static ["cursor","codex","claude"].

## Synthesis
None of these block the architecture; they are scope-precision fixes. Fold them into a revision: (a) auth_kind-branched account semantics, (b) proactive = local-budget/header heuristic, (c) explicit live-roster-id identity through consensus/role/observability. Flag granularity: single AGENT_LAB_DYNAMIC_ROOM flag is correct for single-user; per-capability flags rejected as over-engineering. Dual credential representation is acceptable transitional with accounts[]-first precedence and a documented collapse follow-up.

## Principle check
- P1 (extend not fork): upheld.
- P2 (OFF-parity): upheld (single flag), but require an explicit test that flag-unset == current ["cursor","codex","claude"] behavior.
- P3 (capability honesty): AT RISK until Tension 2 reframed — proactive must not over-claim.
- P4 (always-on floor): upheld (local fallback cooldown-exempt).
- P5 (mock-verifiable): upheld.

## Verdict
WATCH — architecture sound; require revision folding Tensions 1-3 before final ADR.
