# TurnPolicy — signal-driven Room turn effects (implementation history)

> **Status:** shipped implementation reference · current authority: [TURN-CONTRACT.md](./TURN-CONTRACT.md)
> **Flag:** `AGENT_LAB_TURN_POLICY=1` (default **on** since F4; set `0` for legacy)  
> **Related:** [TURN-MODES.md](./TURN-MODES.md) (Plan toggle → deprecated) · [STRUCTURE-REFACTOR-WAVE.md](./STRUCTURE-REFACTOR-WAVE.md)

**Naming:** use **TurnPolicy** — not "auto" (reserved for future model preset auto mode).

## TurnContract rollout

현재 contract, cold start, history, rollout, safety 경계는 [TURN-CONTRACT.md](./TURN-CONTRACT.md)가 소유한다. 아래는 도입 당시 TurnPolicy 문맥이다.

TurnContract adds a deterministic, evidence-backed candidate resolver around TurnPolicy. It classifies the current topic into task kind, risk, and execution intent, scores safe candidates from matching outcome history, and persists one immutable snapshot in `run.json` under `turn_contract`.

`AGENT_LAB_TURN_CONTRACT_MODE` controls adoption:

- `off`: do not apply contract routing.
- `shadow` (default): persist and evaluate the contract without changing the Room roster or rounds.
- `roles`: apply the contract's safe agent limit, round count, and consensus setting.
- `adaptive`: apply those controls only when matching history or deterministic exploration has selected the route.

Cold start uses the bootstrap resolver. History is eligible only after ten context-matching outcomes. Exploration is deterministic and bounded by `AGENT_LAB_FEEDBACK_EXPLORE_RATE`; it can never cross the risk safety floor. Outcome rows record route regret signals including under-routing, over-routing, clarification without delta, FSM without an action, and subset escalation.

---

## Goal

Remove Composer **Plan ON/OFF** and API `mode`/`synthesize` as authorities for side effects. Every Room send runs agents with **permissions SSOT**; Scribe, plan_workflow FSM, and task assign follow **`TurnPolicyEngine.resolve(TurnSignals)`** → **`apply_turn_effects`** (single Scribe choke, F1b).

Human gates unchanged: plan approve, execute 409, worktree, `ask_human` / `propose_build`.

---

## Scribe path inventory (legacy → TurnPolicy)

| Path | Legacy entry | Gate | `scribe_trigger` |
|------|--------------|------|------------------|
| Plan-turn | `_should_scribe_plan_after_turn` | FSM `DRAFT`/`REFINE` only | `plan_workflow_draft` |
| Consensus sync | `maybe_auto_scribe_after_consensus` | `consensus.status==reached` **AND** `pending_agreements>0` | `consensus_reached` |
| Verified loop | `maybe_auto_scribe_after_verified_loop` | `verified_loop.status==done` + idempotent sync | `verified_loop_done` |
| Human override | `synthesize_session_plan` | API `synthesize_only` (dedicated path; ignores `mode`/`synthesize`) | `synthesize_only` |

**F1b:** all paths → **`apply_turn_effects`** once; at most one Scribe LLM call per turn.

---

## TurnSignals

| Field | Source |
|-------|--------|
| `room_preset` | `fast` \| `supervisor` |
| `plan_workflow_phase` | `plan_workflow_phase(run_meta)` |
| `plan_workflow_active` | `is_plan_workflow_active(run_meta)` |
| `consensus_mode` | run meta |
| `consensus_status` | consensus meta `status` |
| `pending_agreement_count` | `len(pending_consensus_agreements(...))` |
| `verified_loop_done` | verified loop terminal + not synced |
| `synthesize_only` | Work 「지금 정리」/ API |
| `cancelled` | run control |
| `supervisor_first_turn` | bootstrap FSM INTAKE→CLARIFY |
| `skill_intent` | slash `/plan` pending · API form · MCP `propose_build` stamp · `[PROPOSED:]` ≥ `AGENT_LAB_PROPOSED_SKILL_INTENT_THRESHOLD` (default 3) |
| `route_category` | `topic_router` category for this turn (P1 TurnContract) |
| `discuss_light` | `run_meta.discuss_light` — supervisor casual discuss, 1 wave |
| `clarity_short_circuit` | concrete anchor / smoke intent — skip CLARIFY |
| `roster_size` | `len(run_meta.agents)` — multi-agent vs single-agent fast path (P2b) |

**P2b:** `TurnPolicyEngine` derives `fast_turn` / `supervisor_turn` from routing signals + roster; `room_preset` is legacy fallback when set.

**P1 snapshot:** `persist_turn_policy_on_run_meta` writes `turn_policy.routing_contract` on `run.json` (`route_category`, `discuss_light`, `clarity_short_circuit`, `skip_fsm_bootstrap`, `fast_turn`, `supervisor_turn`, `roster_size`) for eval trace / `routing_contract` grader.

**Removed (P1):** ~~`legacy_synthesize_hint`~~ — API `mode=plan` / `synthesize=true` no longer opens Scribe.

**MCP (P2):** `plan_phase_advance` — gate owner only; forward targets `CLARIFY`…`HUMAN_PENDING`; `APPROVED` stays Human API.

**MCP (P3):** `run_clarity_interview` — gate owner; 4-axis clarity panel + Human Inbox questions. `execute_propose` — GJC-style alias for `propose_build`. Flag `AGENT_LAB_PLAN_FSM_SKILL_FIRST` default **ON** (`=0` for legacy server auto-tick): vague topics hold CLARIFY until MCP `run_clarity_interview` + `plan_phase_advance`; clarity-threshold-met and cap remain server gate validation fallbacks.

**F1.5 backlog (not F0/F1):** objection-resolve material delta (separate from `[PROPOSED:]` count gate).

Helper: `TurnSignals.from_run_meta(...)` in [`turn_policy.py`](../src/agent_lab/room/turn_policy.py).

---

## TurnEffects

| Field | Meaning |
|-------|---------|
| `run_agent_round` | false only for `synthesize_only` |
| `run_scribe` | invoke Scribe |
| `scribe_trigger` | enum below |
| `advance_plan_workflow` | tick FSM |
| `init_plan_workflow` | supervisor bootstrap |
| `assign_task_owners` | task claim / owner assign |
| `turn_kind` | `agent_turn` \| `plan_side_effect` |

### `scribe_trigger` enum

`none` · `synthesize_only` · `verified_loop_done` · `consensus_reached` · `plan_workflow_draft` · `skill_intent`

### Scribe priority (single winner)

1. `synthesize_only`
2. `verified_loop_done`
3. `consensus_reached` (requires `pending_agreement_count > 0`)
4. `plan_workflow_draft` (phase DRAFT/REFINE, not fast)
5. `skill_intent` (slash/API/MCP `propose_build` / `[PROPOSED:]` threshold, not fast)

**fast preset:** casual send → `run_scribe=false` always (absorbs `AGENT_LAB_AUTO_PLAN_SCRIBE=1` when TurnPolicy ON).

**supervisor preset:** casual send → `run_scribe=false` unless FSM DRAFT/REFINE or other authority signals (same as fast for Scribe).

---

## Decision table

| Preset | Phase | Other | Effects |
|--------|-------|-------|---------|
| fast | inactive | casual | no scribe, no FSM |
| fast | inactive | `synthesize_only` | scribe only |
| supervisor | INTAKE | first turn | `init_plan_workflow`, advance, no scribe |
| supervisor | CLARIFY | — | advance, no scribe |
| supervisor | DRAFT/REFINE | — | scribe + advance |
| supervisor | HUMAN_PENDING | — | no scribe |
| any | — | consensus reached + pending>0 | scribe `consensus_reached` |
| any | — | consensus reached + pending==0 | **no scribe** |
| any | — | verified loop done | scribe `verified_loop_done` |

**Task assign:** `consensus_mode OR run_scribe OR phase in {DRAFT, REFINE, PEER_REVIEW}`.

---

## `mode` / `synthesize` consumer inventory (F1b)

| Location | Replacement |
|----------|-------------|
| `turn_flow.py` `mode = plan if synthesize` | `turn_kind` + TurnEffects |
| `is_discuss_only_turn` → lead block | `not assign_task_owners && !consensus_mode` |
| `should_assign_tasks_on_turn` | `TurnEffects.assign_task_owners` |
| `resolve_send_receipt` | derive from TurnEffects + FSM |
| `tasks.sync_tasks_after_turn` | TurnEffects |
| `should_enable_plan_workflow(synthesize)` | `init/advance_plan_workflow` |
| `plan_workflow_allows_scribe(synthesize)` | `TurnEffects.run_scribe` |
| `room.py` Form fields | deprecated hints → F4 remove |

**run.json (F4):** `turn_policy` snapshot + `turn_kind`; deprecate `_active_turn_mode` / `_active_synthesize`.

---

## Permissions (F1a / F2)

[`_effective_discuss_permissions`](../src/agent_lab/room/messages.py):

- **Remove:** `apply_discuss_executor_policy(discuss=True)` on Room path (F1a)
- **Keep:** `apply_discuss_workspace(perms, binding)` (F1a — `_effective_room_permissions`)

Execute lane unchanged: `PolicyEngine`, 409, `propose_build`, worktree.

---

## Phases

| Phase | Deliverable |
|-------|-------------|
| **F0** | `turn_policy.py`, this doc, `tests/test_turn_policy.py` |
| **F1a** | permissions leak min fix |
| **F1b** | `apply_turn_effects` wired in `turn_flow.py` |
| **F2** | overlay / lead block cleanup |
| **F3** | UI Plan toggle removal (after Wave A) |
| **F4** | API cleanup + default flag ON + dual-run |
| **F5** | smoke + extended regression |

---

## F0 test matrix (`tests/test_turn_policy.py`)

| Case | Expect |
|------|--------|
| fast + AUTO_PLAN_SCRIBE=1 + legacy hint false | `run_scribe=False` |
| consensus reached + pending=0 | `run_scribe=False` |
| consensus reached + pending>0 | `run_scribe=True`, trigger `consensus_reached` |
| verified_loop_done | `run_scribe=True`, trigger `verified_loop_done` |
| supervisor first turn | `init_plan_workflow=True` |
| synthesize_only | `run_scribe=True`, `run_agent_round=False` |
| `apply_turn_effects` when flag off | `applied=False`, `detail=turn_policy_disabled` |
| `apply_turn_effects` when flag on (F0) | `applied=False`, `detail=f0_stub_no_side_effects` |

---

## Verification (F4 pre-flip)

```bash
make test-fast
AGENT_LAB_TURN_POLICY=1 pytest tests/test_turn_policy.py tests/test_plan_workflow.py tests/test_verified_loop.py tests/test_room_team_orchestration.py -q
python scripts/smoke_room.py  # L768 → turn_policy snapshot (F5)
```

Dual-run: same fixture with `AGENT_LAB_TURN_POLICY=0` vs `=1`.
