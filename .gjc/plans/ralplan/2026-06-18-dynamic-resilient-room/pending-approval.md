# RALPLAN Final Plan (pending approval) — Dynamic Resilient Multi-Agent Room

Run: 2026-06-18-dynamic-resilient-room | Consensus: 2 passes | Architect CLEAR/APPROVE | Critic APPROVE
Source spec: .gjc/specs/deep-interview-dynamic-resilient-agent-room.md
Mode: deliberate (auth/security surface)

## Goal
Extend agent-lab's multi-agent Room so that when one or two models hit usage limits, at least one agent always runs and base functionality continues uninterrupted — via per-provider multi-account failover, availability-driven dynamic roster, role reallocation with consensus floor 2 / 1-agent solo, capability-aware (local-heuristic) usage detection, a local/offline fallback floor, and 6 slash commands; all additive and flag-gated for OFF-parity.

## ADR
- **Decision**: Additive, flag-gated (AGENT_LAB_DYNAMIC_ROOM) extension of existing credential_store / consensus_gate / room.run_room / cost_ledger, with new leaf modules (provider_registry, account_chain, usage_monitor, agent_roster, slash_commands). (Option 1)
- **Drivers**: resilience (never 0 agents); brownfield safety (no regression); single-user local dogfooding with mock-only verification.
- **Alternatives considered**: Option 2 full credentials.toml migration to accounts[]-only — rejected (destructive, non-reversible, breaks OFF-parity, no dogfooding benefit; Option 1 reaches the same end state additively).
- **Why chosen**: matches the repo's proven flag-gated additive pattern (AGENT_LAB_PIPELINE), bounded blast radius, reversible, independently mock-testable.
- **Consequences**: transitional dual credential representation (accounts[] + legacy primary/fallback); new leaf modules; dynamic path behind a flag until dogfooded.
- **Follow-ups**: proactive local-budget threshold default; local fallback model/endpoint default; OAuth spare-profile between-turn switch mechanics; collapse dual representation post-dogfooding; AGENT_LAB_DYNAMIC_ROOM default-on after dogfooding.

## Principles
1. Extend, don't fork. 2. OFF-parity & reversibility (additive, flag-gated). 3. Capability honesty (proactive = local budget/header heuristic, never server-quota; OAuth/CLI reactive-only). 4. Always-on floor (local fallback, consensus floor 2, solo at 1). 5. Mock-verifiable.

## Architecture seams
- **auth_kind branch** (the critical seam): provider_registry.auth_kind in {api, local, oauth, cli}.
  - api/local (KIMI, cursor-API, local): secret-string N-account chain, in-turn rotation on failure, per-account cooldown.
  - oauth/cli (claude, codex): ONE active CLI OAuth profile; accounts[] holds profile refs (not secrets); on failure -> seat substitution to next provider (NO in-turn key rotation); spare profile activated only between turns (best-effort).
- **Live roster identity**: agent_roster.select_roster() returns concrete live agent ids; consensus_gate, role allocation, run.json observability, /agents all use live ids — never the static default names.
- **Floor**: local fallback is always-available + cooldown-exempt, lowest substitution priority -> guarantees >=1 agent.

## Implementation Phases
1. **provider_registry.py** + additive credential_store accounts[] (load/save, accounts[]-first then legacy; mask_secret reuse). Register KIMI (api, usage_exposing) + local (local, always-available).
2. **account_chain.py** (auth_kind-branched chain + cooldown) + **usage_monitor.py** (proactive = cost_ledger local budget cap / usage headers for usage-exposing; reactive via is_credential_failure for all; cooldown gated on confirmed credential failure only).
3. **agent_roster.py** + room adapter behind AGENT_LAB_DYNAMIC_ROOM (default cursor+codex+claude; substitution KIMI->local; /model override). OFF = current hardcoded behavior.
4. **consensus_gate** extension: allocate_roles (propose->endorse->synthesize->scribe fill on live ids); effective_consensus (floor 2; size 1 => solo/consensus-off). Reuse default_consensus_policy.
5. **slash_commands.py** + room router: /login /logout /accounts(masked) /model /usage /agents; writes via credential_store; Settings UI credential write reduced to read-only status (public_credentials_payload retained, patch_from_request write gated/disabled).
6. **local fallback provider** (Ollama/OpenAI-compatible) registration + mock adapter; endpoint/model a tunable default.

## Acceptance Criteria (mock, AGENT_LAB_MOCK_AGENTS=1)
- [ ] 1a api/local: account 1 quota error -> in-turn switch to account 2 -> 3...
- [ ] 1b oauth/cli: profile failure -> NO in-turn key rotation; seat substitution to next provider; spare profile only next turn.
- [ ] 2 model exhaustion -> seat substitution (KIMI->local).
- [ ] 3 3->2 consensus floor (both endorse).
- [ ] 4 2->1 solo mode (consensus off, single output accepted).
- [ ] 5 cooldown retry (only on is_credential_failure; local fallback exempt).
- [ ] 6 slash 6 commands functional; writes unified to slash; secrets masked.
- [ ] 7 proactive preemption = local budget/usage-header heuristic for usage-exposing providers only; OAuth/CLI never preempt.
- [ ] 8 local fallback guarantees >=1 agent when all cloud exhausted.
- [ ] 9 make test-fast green == baseline + new.
- [ ] 10 OFF-parity named test: AGENT_LAB_DYNAMIC_ROOM unset == ["cursor","codex","claude"] + byte-stable consensus.

## Pre-mortem mitigations (carried)
- Secret/token leak -> mask_secret, profile-refs-not-tokens for OAuth, no secret logging.
- Cooldown strands all accounts -> cooldown only on confirmed credential failure, bounded TTL, local fallback cooldown-exempt.
- Roster/consensus mis-set -> deterministic substitution with hard stop at local fallback; single floor=2 helper; explicit solo branch; 3/2/1 transition tests.

## Verification
Per-phase mock unit/integration tests; e2e mock (2 of 3 providers raise quota -> turn completes with >=1 agent); make test-fast green; ruff clean; mypy no new errors; OFF-parity named test.

## Status: PENDING APPROVAL
No execution performed. Awaiting explicit approval to proceed (recommended: ultragoal). Per pipeline discipline, execution is a separate approval-gated step.
