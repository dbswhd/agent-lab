# Critic Evaluation (stage_n 1) — Dynamic Resilient Multi-Agent Room

## Verdict: ITERATE

## Quality assessment
- Principle-option consistency: PASS — Option 1 follows P1/P2/P4/P5.
- Fair alternatives: PASS — Option 2 stated and invalidated on risk/benefit, not strawmanned.
- Risk mitigation clarity: PASS — pre-mortem mitigations are concrete (cooldown gated on is_credential_failure, local fallback cooldown-exempt, single floor helper).
- Testable acceptance criteria: PASS — maps to spec's 7 mock scenarios.
- Concrete verification: PASS — per-phase mock tests + make test-fast + OFF-parity.

## Why ITERATE (must address before APPROVE)
1. **Capability-honesty violation (P3) is currently latent in the plan text.** The Architect is right: Phase 2 "proactive usage/token threshold" reads as server-quota knowledge. As written it would let an implementer claim something cost_ledger cannot deliver. REQUIRE the revision to state proactive = local budget cap / provider usage-header heuristic explicitly. Without this the plan can pass tests while misrepresenting the capability.
2. **OAuth N-account is under-specified and currently testable-false.** Acceptance criterion "N-account sequential failover" applied uniformly would produce tests that pretend codex can rotate two OAuth key strings in-turn — which is impossible per get_credential_chain returning [] for OAUTH_ONLY. REQUIRE auth_kind-branched semantics so the N-account test for oauth providers asserts the *correct* behavior (one active profile + cross-seat/next-provider reactive failover), not a fictional key rotation.
3. **OFF-parity needs an explicit named test, not just a claim.** REQUIRE an acceptance item: with AGENT_LAB_DYNAMIC_ROOM unset, room agent selection is exactly ["cursor","codex","claude"] and consensus_gate behavior is unchanged (byte-stable path).

## Not blocking (acknowledge in ADR follow-ups)
- Dual credential representation longevity — fine transitional.
- Proactive threshold numeric default — already a deferral.
- Local fallback model/endpoint default — already a deferral.

## Required for APPROVE
Revise plan to: (a) reframe proactive as local-budget/header heuristic (P3), (b) branch account semantics by auth_kind with correct oauth failover behavior, (c) add explicit OFF-parity acceptance test. Re-run Architect + Critic.
