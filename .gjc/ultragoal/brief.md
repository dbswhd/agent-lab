Dynamic Resilient Multi-Agent Room for agent-lab. Approved ralplan plan: .gjc/plans/ralplan/2026-06-18-dynamic-resilient-room/pending-approval.md. Spec: .gjc/specs/deep-interview-dynamic-resilient-agent-room.md.

SHARED CONSTRAINTS (apply to every story):
- Additive & flag-gated behind AGENT_LAB_DYNAMIC_ROOM; OFF (flag unset) == current ["cursor","codex","claude"] behavior byte-stable.
- Reuse/extend existing modules (no parallel subsystems): credential_store.py (additive accounts[] + legacy primary/fallback), consensus_gate.py, room.run_room/room_turn_flow.py, cost_ledger.py.
- auth_kind seam: api/local providers (KIMI/cursor-API/local) get in-turn secret N-account rotation; oauth/cli (claude/codex) get ONE active CLI OAuth profile + seat-substitution failover, NO in-turn key rotation, accounts[] holds profile refs not secrets (get_credential_chain returns [] for OAUTH_ONLY).
- Proactive usage detection = cost_ledger LOCAL budget cap / usage-header heuristic (never server-quota); OAuth/CLI reactive-only via is_credential_failure; cooldown only on confirmed credential failure; local fallback cooldown-exempt to guarantee >=1 agent.
- Verification MOCK-ONLY (AGENT_LAB_MOCK_AGENTS=1); do not depend on live agents.
- Conventions: from __future__ import annotations first line; routers only under app/server/routers/; run.json via patch_run_meta; run-lock via run_control.
- Per-goal gates: make test-fast green == baseline+new, ruff clean, mypy no new errors, OFF-parity named test. Do not commit/push unless asked.

@goal: Provider registry + additive N-account credential store
Add src/agent_lab/provider_registry.py declaring providers cursor/claude/codex/kimi/local with auth_kind (api/oauth/cli/local), usage_exposing bool, fallback_class. Extend credential_store.py additively: per-provider accounts[] (label, secret_or_profile_ref, priority, cooldown_until) in load/save while keeping legacy primary/fallback readable; get_account_chain(provider) returns ordered cooldown-filtered entries (accounts[] first, then legacy). Reuse mask_secret/_escape_toml/env mirroring. Register KIMI (api, usage_exposing=true, OpenAI-compatible) and local (local, always-available). Mock unit tests for load/save additive parsing and chain ordering.

@goal: Account chain + capability-aware usage monitor with cooldown
Add src/agent_lab/account_chain.py (auth_kind-branched chain: api/local secret N-rotation in-turn; oauth/cli single active profile, no in-turn key rotation) and src/agent_lab/usage_monitor.py (should_preempt = cost_ledger LOCAL budget cap / usage-header heuristic, only for usage_exposing providers; mark_exhausted sets cooldown_until only on is_credential_failure; cooldown_active gate; local fallback exempt). Mock unit tests for per-auth_kind branching, cooldown skip/expiry, proactive-only-for-usage_exposing.

@goal: Dynamic agent roster + room adapter (flag-gated)
Add src/agent_lab/agent_roster.py select_roster(): default cursor+codex+claude, substitution priority KIMI->local for empty/unavailable seats, /model override of composition + substitution priority; availability from registry is_available + non-empty account chain + not fully cooled. Wire room.run_room behind AGENT_LAB_DYNAMIC_ROOM to consult select_roster() (OFF = hardcoded current behavior). Mock tests for default composition, substitution priority, and OFF-parity named test (flag unset == ["cursor","codex","claude"]).

@goal: Role reallocation + consensus floor and solo mode
Extend consensus_gate.py: allocate_roles(agents) fill order propose->endorse->synthesize->scribe on LIVE roster ids; effective_consensus(agents) enforces floor=2; size 1 => solo mode (consensus disabled, single-agent output accepted). Reuse default_consensus_policy. Operate on live roster ids never static default names. Mock tests for 3/2/1 transitions and floor enforcement.

@goal: Slash commands + Settings UI read-only
Add src/agent_lab/slash_commands.py + wire through app/server/routers/room.py: /login <provider>, /logout <provider>, /accounts <provider> (list/add/remove, masked via mask_secret), /model (view/switch composition + substitution priority), /usage (per-account usage + cooldown state), /agents (current roster + roles). Writes via credential_store. Reduce Settings UI credential write (patch_from_request) to read-only status (public_credentials_payload retained). Mock tests for all 6 command parses + masked output + write path.

@goal: Local fallback provider + e2e resilience
Register local (Ollama/OpenAI-compatible) provider as always-available, cooldown-exempt, lowest substitution priority; mock adapter for tests. Endpoint/model a tunable default. E2E mock test (AGENT_LAB_MOCK_AGENTS=1): 2 of 3 providers raise quota errors -> room completes a turn with >=1 agent and valid (or solo) consensus outcome; full-cloud-exhaustion -> local fallback keeps >=1 agent.
