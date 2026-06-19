# Plan (Planner / deliberate): Dynamic Resilient Multi-Agent Room

Source spec: .gjc/specs/deep-interview-dynamic-resilient-agent-room.md (ambiguity 6%, PASSED)

## RALPLAN-DR Summary

### Principles (5)
1. Extend, do not fork — reuse credential_store / consensus_gate / room.run_room / room_turn_flow / cost_ledger; zero parallel subsystems.
2. OFF-parity & reversibility — existing default 3-agent (cursor+codex+claude) flow byte-stable unless the new dynamic path is actually engaged; all data-model changes additive (no destructive credentials.toml migration).
3. Capability honesty — never claim proactive usage detection for a provider that cannot expose remaining usage; OAuth/CLI providers are reactive-failover only.
4. Always-on floor — local/offline fallback guarantees >=1 agent; consensus floor = 2; at 1 agent run solo with consensus disabled.
5. Mock-verifiable — every behavior provable under AGENT_LAB_MOCK_AGENTS=1; no live-mission dependency.

### Decision Drivers (top 3)
1. Resilience: the room must never reach 0 agents when 1-2 models exhaust.
2. Brownfield safety: no regression to the working room/consensus/credential paths.
3. Single-user local dogfooding with mock-only verification.

### Viable Options
**Option 1 (RECOMMENDED): Additive account-list extension + new leaf modules, flag-gated dynamic path.**
- credentials.toml gains an additive per-provider `accounts = [{label, secret_or_profile, priority, cooldown_until}]` array; legacy `primary`/`fallback` keys remain readable and are folded into the chain. `get_credential_chain` walks `accounts[]` (skipping cooled-down) then legacy primary->env->fallback->env.
- New leaf modules: `provider_registry.py` (provider metadata: auth_kind, usage_exposing, fallback class), `account_chain.py` (N-account + cooldown), `usage_monitor.py` (capability-aware proactive/reactive), `agent_roster.py` (dynamic seat selection + substitution/shrink), `slash_commands.py` (6 commands). consensus_gate gains a floor/solo helper. room adapter wires roster into run_room behind a dynamic flag.
- Pros: backward compatible, OFF-parity, reversible, matches the repo's established flag-gated additive pattern; each module independently mock-testable.
- Cons: dual credential representation (accounts[] + legacy) during transition; more modules.

**Option 2: Full credentials.toml schema migration to accounts[] only.**
- Replace primary/fallback with accounts[] everywhere; one-shot migrator.
- Pros: single clean representation.
- Cons: destructive migration, breaks OFF-parity and rollback, risk to a working auth path, higher blast radius for a single-user tool. **Invalidated**: the resilience goal does not require dropping the legacy keys, and migration adds risk with no dogfooding benefit; Option 1 reaches the same end state additively and reversibly.

Single-option convergence is NOT claimed — Option 2 is viable but rejected on risk/benefit.

### Pre-mortem (deliberate — auth/security surface)
1. **OAuth/secret leak**: `/accounts` listing or logs print raw secrets/OAuth tokens. Mitigation: reuse `mask_secret`; `/accounts` shows masked + label only; never log secrets; OAuth providers store a profile reference, not a token, in accounts[].
2. **Cooldown strands all accounts (false-exhausted)**: a transient error marks every account cooled-down, the provider goes dark, and with all providers cooled the room hits 0 agents. Mitigation: cooldown only on confirmed quota/credential-failure patterns (reuse `is_credential_failure`), not generic errors; bounded cooldown TTL with immediate retry-on-next-turn once elapsed; local fallback is exempt from cooldown so >=1 agent always remains.
3. **Roster/consensus mis-set**: substitution loops forever, or consensus floor lets a single endorsement pass as "consensus", or 3->1 silently keeps requiring 3 endorsements and deadlocks. Mitigation: deterministic substitution order with a hard stop at the local fallback; consensus floor constant = 2 enforced in one helper; explicit solo-mode branch at size 1 that disables consensus; unit tests for 3/2/1 transitions.

### Expanded Test Plan (deliberate)
- **Unit**: account_chain ordering + cooldown skip/expiry; is_credential_failure gating of cooldown; usage_monitor proactive-only-for-usage_exposing + reactive failover; roster default composition + substitution priority (KIMI->local); role reallocation fill order; consensus floor (2 endorse) + solo (1) ; slash command parsing for all 6.
- **Integration**: room turn with provider exhausted mid-chain -> account failover; full-provider exhaustion -> seat substitution -> shrink -> local fallback; consensus_gate at sizes 3/2/1; credentials.toml additive load (legacy primary/fallback still honored).
- **E2E (mock)**: AGENT_LAB_MOCK_AGENTS=1 simulated room run where 2 of 3 providers raise quota errors and the room still completes a turn with >=1 agent and a valid (or solo) consensus outcome.
- **Observability**: `/usage` reflects per-account cooldown state and proactive threshold status; roster/role decisions recorded on run.json via patch_run_meta (reuse goal_ledger-style append) for post-hoc inspection; no secret values in any recorded field.

## Implementation Phases

### Phase 1 — Provider registry + N-account chain (additive)
- `provider_registry.py`: declare providers cursor/claude/codex/kimi/local with `auth_kind` (api/oauth/cli/local), `usage_exposing` (bool), `fallback_class` (primary|spare|local).
- Extend `credential_store.py`: additive `accounts[]` per provider in load/save (keep primary/fallback); `get_account_chain(provider)` returns ordered, cooldown-filtered (label, secret_or_profile) with legacy keys appended. Keep `get_credential_chain` working (delegate).
- Reuse `mask_secret`, `_escape_toml`, env mirroring. KIMI registered as OpenAI-compatible API (usage_exposing=true); local as OpenAI-compatible offline (always available).

### Phase 2 — Usage monitor (capability-aware) + cooldown
- `usage_monitor.py`: `should_preempt(provider, account)` true only when `usage_exposing` and tracked usage (via cost_ledger) >= threshold; `mark_exhausted(provider, account)` sets cooldown_until on confirmed `is_credential_failure`; `cooldown_active(account)` gate. Wire into the call path so the chain skips cooled/preempted accounts and reactive failover advances on credential failure.

### Phase 3 — Dynamic agent roster + room adapter (flag-gated)
- `agent_roster.py`: `select_roster()` picks up to 3 available agents — default cursor+codex+claude, substitution priority KIMI->local for empty seats; `/model` override of composition + substitution priority. Availability from registry `is_available` + account chain non-empty + not fully cooled.
- Room adapter: behind a dynamic flag (e.g. AGENT_LAB_DYNAMIC_ROOM), `room.run_room` consults `select_roster()` instead of the hardcoded `["cursor","codex","claude"]`; OFF = current behavior.

### Phase 4 — Role reallocation + consensus floor/solo
- consensus_gate: `allocate_roles(agents)` fill order propose->endorse->synthesize->scribe; `effective_consensus(agents)` enforces floor 2; size 1 => solo mode (consensus disabled, single-agent output accepted). Reuse `default_consensus_policy`.

### Phase 5 — Slash commands + Settings UI read-only
- `slash_commands.py` + room router wiring: `/login <provider>`, `/logout <provider>`, `/accounts <provider>` (list/add/remove, masked), `/model` (view/switch composition + substitution priority), `/usage` (per-account usage + cooldown), `/agents` (current roster + roles). Writes go through credential_store. Settings UI credential POST reduced to read-only status (`public_credentials_payload` stays; `patch_from_request` write disabled or gated).

### Phase 6 — Local fallback provider
- Register local (Ollama/OpenAI-compatible) as always-available, cooldown-exempt, lowest substitution priority; mock adapter for tests. Provider endpoint/model is a tunable default (deferral).

## ADR (draft — finalized at consensus)
- Decision: additive, flag-gated extension of existing credential/room/consensus modules (Option 1).
- Drivers: resilience, brownfield safety, mock-only verification.
- Alternatives considered: full schema migration (Option 2) — rejected (destructive, non-reversible, no dogfooding benefit).
- Consequences: dual credential representation during transition; new leaf modules; dynamic path flag-gated for OFF-parity.
- Follow-ups: proactive threshold default numerics; local fallback model/endpoint default; OAuth multi-profile mechanics; later flag default-on after dogfooding.

## Acceptance Criteria (from spec, mock AGENT_LAB_MOCK_AGENTS=1)
N-account failover; model-exhaustion->seat substitution (KIMI->local); 3->2 consensus floor; 2->1 solo; cooldown retry; slash 6 commands; proactive threshold (usage-exposing only); local fallback >=1 agent; OFF/regression safety (make test-fast green).

## Verification
Per-phase mock unit/integration tests; full `make test-fast` green == baseline+new; ruff clean; mypy no new errors; OFF-parity (dynamic flag unset == current behavior).

## Open Tensions for Architect
1. OAuth multi-account: claude/codex auth is CLI OAuth (get_credential_chain returns [] today). N-account for OAuth = multiple CLI OAuth profiles, not secret strings — needs a profile-switch mechanism vs. API-key chain. Is profile switching feasible per turn, or is OAuth limited to 1 active profile + reactive failover to a spare API/local?
2. Dual credential representation (accounts[] + legacy primary/fallback) longevity — acceptable transitional, or collapse later?
3. Flag granularity — one AGENT_LAB_DYNAMIC_ROOM flag vs per-capability flags.
