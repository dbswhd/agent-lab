# Deep Interview Spec: Dynamic Resilient Multi-Agent Room

## Metadata
- Interview ID: 019ed548-d08e-7000-b7c5-762a5da23e4e
- Rounds: 10 (+1 restate loop)
- Final Ambiguity Score: 6%
- Type: brownfield
- Generated: 2026-06-18T12:31:00Z
- Threshold: 0.05
- Threshold Source: default
- Initial Context Summarized: no
- Status: PASSED (all-dimensions >=0.9 escalation; ambiguity 6% vs 5% threshold, residual = tunables deferred)
- Auto-Researched Rounds: []
- Auto-Answered Rounds: []
- Architect Failures: 0
- Lateral Reviews: 0 convened (subagent dispatch unavailable; contrarian/simplifier/researcher lenses folded into rounds 5,6,7)
- Lateral Panel Failures: 2
- Refined Rounds: [2, 11]
- Closure Overrides: none
- Restated Goal: agent-lab multi-agent Room extended with per-provider multi-account sequential failover + cooldown retry, availability-driven dynamic roster (default Cursor+Codex+Claude, substitution KIMI->local fallback), role auto-reallocation with consensus floor 2 and 1-agent solo mode, capability-aware usage detection (proactive for usage-exposing providers + reactive for OAuth/CLI), and 6 slash-command auth management (usage via /usage only, Settings UI read-only auth status), so that even if one or two models hit limits at least one agent always runs and base functionality continues uninterrupted.

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.93 | 0.35 | 0.326 |
| Constraint Clarity | 0.93 | 0.25 | 0.233 |
| Success Criteria | 0.93 | 0.25 | 0.233 |
| Context Clarity | 0.93 | 0.15 | 0.140 |
| **Total Clarity** | | | **0.932** |
| **Ambiguity** | | | **0.068** |

## Topology
| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| Account & credential registry | active | Multi-account/multi-provider credentials + slash-command login | N-account chain, OAuth/CLI/API mix, cooldown retry, 6 slash cmds, Settings UI->read-only migration (R2,4,6,10,11) |
| Dynamic agent roster | active | Runtime availability-based 3-agent selection + seat substitution/shrink | Default Cursor+Codex+Claude, substitution KIMI->local, /model override (R1,8) |
| Role allocation engine | active | propose/endorse/synthesize/scribe allocation + reallocation on shrink | Auto-reallocation by live count, consensus floor 2, 1-agent solo (R3) |
| Usage & token budget manager | active | Per-account usage/limit tracking + auto failover | Capability-aware hybrid detection (proactive for usage-exposing + reactive error failover for OAuth/CLI), cooldown (R2,5) |
| Room runtime adapter | active | Wire components into room.run_room/room_turn_flow | Provider adapter interface + local fallback, stable 3-agent facade (R7,9) |

## Established Facts
1. (R1) On full model exhaustion: substitute spare model into seat to keep 3; else shrink roster.
2. (R2) Detection = proactive usage/token threshold + reactive credential-error failover.
3. (R2) Auth: claude/codex OAuth (CLI, OAUTH_ONLY), cursor API key; KIMI new provider.
4. (R2 context) Codebase already has primary->fallback (2-account) chain + reactive failover (call_with_credential_fallback, is_credential_failure) + Settings-UI login. Deltas = N-account, slash login, KIMI, dynamic roster.
5. (R3) Role auto-reallocation (propose->endorse->synthesize fill); consensus floor = 2; 1 agent = consensus off, solo execution.
6. (R4) Account chain = unlimited N sequential; exhausted account skipped then auto-retried after cooldown (usage-window reset aware).
7. (R5) Proactive threshold only for usage-exposing providers (KIMI/cursor API); OAuth/CLI (claude/codex/cursor-agent) reactive error failover only (capability-aware refinement of R2).
8. (R6) Slash commands = /login /logout /accounts /model /usage /agents (6).
9. (R7) Provider scope = Codex/Claude/Cursor/KIMI (KIMI OpenAI-compatible API, proactive eligible) + local/offline fallback (Ollama/OpenAI-compatible, guarantees >=1 agent); adapter interface open for future providers.
10. (R8) Default roster = Cursor+Codex+Claude (when unspecified); /model overrides composition + substitution priority; default substitution priority KIMI->local.
11. (R9) Acceptance = mock (AGENT_LAB_MOCK_AGENTS=1) 7 scenarios green.
12. (R10) Migration: slash commands primary write surface, Settings UI read-only status, shared credential_store.
13. (R11 non-goal) No dedicated usage-display UI (incl. usage-exposing providers). Usage via /usage only. Settings UI read-only retained for credential/login state.

## Trigger Metadata
- R2: candidate trigger D (scope expansion, credential-registry OAuth/CLI auth) -> reclassified as convergence after confirming codebase already has OAuth+failover; ambiguity dropped 59->48. No penalty.
- R5: refined R2 "both" into capability-aware; not a contradiction, no trigger.
- R1,R3,R4,R6,R7,R8,R9,R10: no triggers, monotonic decrease.

## Lateral Review Panel
- Subagent dispatch unavailable -> panels not convened (lateral_panel_failures=2). Persona lenses folded by orchestrator: R5 contrarian (proactive feasibility), R6 simplifier (minimal command set), R7 researcher (additional providers/local fallback).

## Goal
Extend agent-lab's multi-agent Room to be dynamic and resilient so that even when one or two models hit usage limits, at least one agent always runs and base functionality continues uninterrupted. Specifically implement per-provider multi-account sequential failover, availability-driven dynamic roster, role auto-reallocation on shrink (consensus floor 2, 1-agent solo), capability-aware usage detection, and 6 slash commands for auth/account/model/usage management.

## Constraints
- Single-user local dogfooding (deployment/multiuser out of scope).
- Reuse/extend existing credential_store.py (primary->fallback, OAUTH_ONLY providers, call_with_credential_fallback), consensus_gate.py, room.run_room/room_turn_flow (no parallel implementations).
- Mock-only verification (AGENT_LAB_MOCK_AGENTS=1); live missions not guaranteed due to agent limits.
- Routers under app/server/routers/, run.json via patch_run_meta, run-lock via run_control.
- Proactive threshold applies only to usage-exposing providers (OAuth/CLI cannot -> reactive failover only).
- Consensus floor 2; at 1 agent run solo (consensus disabled).

## Non-Goals
- New dedicated usage-display UI (incl. usage-exposing providers) -- usage via /usage slash command only.
- Credential writes from Settings UI (reduced to read-only status).
- Deployment/hosting/multiuser/remote auth.
- First-pass implementation of extra cloud providers (Gemini/DeepSeek/Qwen) -- adapter interface only, deferred.

## Acceptance Criteria (mock, AGENT_LAB_MOCK_AGENTS=1)
- [ ] N-account sequential failover: provider account 1 credential/quota error -> auto switch to 2->3...
- [ ] Model exhaustion -> seat substitution: full provider exhaustion fills seat from fallback pool (KIMI->local) keeping 3 agents.
- [ ] 3->2 consensus floor: with 2 agents, mutual endorsement forms consensus.
- [ ] 2->1 solo mode: with 1 agent, consensus disabled, solo execution keeps base functionality.
- [ ] Cooldown retry: exhausted account auto-rejoins chain after cooldown.
- [ ] Slash 6 commands: /login /logout /accounts /model /usage /agents work; writes unified to slash.
- [ ] Proactive threshold (usage-exposing only): KIMI/cursor-API accounts pre-switch at threshold; OAuth/CLI reactive only.
- [ ] Local fallback guarantee: all cloud accounts exhausted -> local/offline fallback keeps >=1 agent.
- [ ] OFF/regression safety: existing 3-agent behavior and consensus_gate no regression (make test-fast green).

## Deferrals
- Proactive threshold default numerics (e.g. 10% remaining / N tokens): tunable default at implementation.
- Local fallback model selection (Ollama model/endpoint): environment-dependent default.
- Additional cloud providers (Gemini/DeepSeek/Qwen): adapter interface opened first-pass, implementation deferred.
- Convergence Pacing: no min-round floor/score-drop cap/dampening -- bidirectional scoring is the pacing mechanism.

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| Credentials = simple API keys | User: "mainly OAuth, some CLI" | Codebase already supports OAUTH_ONLY+API key mix -> converge as extension |
| "proactive+reactive" for all providers | contrarian: OAuth/CLI expose no remaining quota | Capability-aware hybrid -- proactive only for exposing providers |
| Empty seat always substituted | What if no spare model? | Situational: substitute first, shrink if none; local fallback guarantees final >=1 |
| Accounts fixed at 2 (primary+fallback) | User: "many accounts, 1 used up -> 2" | Unlimited N sequential + cooldown retry |
| Login via Settings UI | User: "switch to / commands" | Slash primary write, UI read-only; no new usage UI |

## Technical Context (brownfield)
- src/agent_lab/credential_store.py: providers cursor/claude/codex, OAUTH_ONLY_PROVIDERS={claude,codex}, primary->env->fallback->env chain (get_credential_chain), call_with_credential_fallback, is_credential_failure, public_credentials_payload/patch_from_request (Settings).
- src/agent_lab/codex_oauth.py, agent_auth_bootstrap.py: Codex OAuth capture + startup auth bootstrap (bootstrap_room_auth_on_startup, warm_claude_auth_cache).
- src/agent_lab/agents/registry.py: codex_cli/claude_cli/cursor_agent delegation (is_available, model_label, call_agent/call_agent_reply).
- src/agent_lab/consensus_gate.py: consensus_gate_met, default_consensus_policy, normalize_consensus_signal/sync_consensus_snapshot (Room->run.consensus).
- src/agent_lab/room.py / room_turn_flow.py: turn orchestration; cost_ledger.py: cost/usage tracking.
- Delta summary: (a) 2-account->N-account chain, (b) new provider KIMI (OpenAI-compatible)+local fallback, (c) dynamic roster+seat substitution/shrink, (d) role reallocation+consensus floor, (e) capability-aware proactive detection, (f) Settings writes->6 slash commands.

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| Provider | core domain | id, auth_kind(oauth/api/cli/local), usage_exposing(bool) | has many Account; mapped to Agent seat type |
| Account | core domain | provider_id, label, secret/oauth_token, priority, cooldown_until | belongs to Provider; ordered in failover chain |
| Seat | core domain | index(1-3), assigned_agent, role | filled by Agent; part of Roster |
| Agent | core domain | provider, model_label, available | occupies Seat; performs Role |
| Role | supporting | kind(propose/endorse/synthesize/scribe) | assigned to Agent; reallocated on roster change |
| Roster | core domain | seats[], size(1-3), default_composition | composed of Seats; degrades/substitutes |
| UsageBudget | supporting | provider_id, account_id, threshold, mode(proactive/reactive) | tracks Account; triggers failover |
| ConsensusPolicy | supporting | floor(2), endorse_count | gates Roster turns; disabled at size 1 |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 1 | 6 | 6 | - | - | N/A |
| 2 | 7 | 1 | 0 | 6 | 100% |
| 5+ | 8 | 1 | 0 | 7 | 100% |

## Interview Transcript
Rounds 0-11 summarized in Established Facts and Assumptions tables above. Ambiguity trajectory: 100->59->48->37->32->27->23->19->15->9->7->6%.
