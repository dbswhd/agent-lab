# Agent OS Mode Simplification Plan

Status: shipped through P1/P2 on 2026-06-15 (mode contract, plan_intent approval gate, model_id readiness).

## Summary

Agent Lab keeps the Agent OS runtime shape: Room discussion, plan.md, Human approval, worktree execute, merge review, and Oracle/verified loop. The product issue is that the old UI exposed Quick, Analyze, Split, and infinity while backend behavior also depended on `mode`, `turn_profile`, `agent_rounds`, `review_mode`, and `consensus_mode`.

The new user-facing contract is:

| User mode | Agents | Plan policy | Runtime behavior |
| --- | --- | --- | --- |
| Quick | 1 lead agent | optional | R1 only by default; plan toggle can write/update plan.md. |
| Team | selected team | optional | 3-agent default, R1 only; with plan on, plan.md is updated but execute/verify loop is not started. |
| Loop | selected team | required | consensus/specialist/verified topology plus plan, execute, Human/Oracle gates, and bounded verify loop. |

`verified` maps to `Loop`, not `Team`. The old frontend behavior that normalized `verified` to `analyze` is treated as a bug because `verified` means iterate, verify, and gate.

## Legacy Migration

| Legacy input | New mode | Notes |
| --- | --- | --- |
| `quick` | `quick` | Lead agent only, R1. |
| `analyze` | `team` | One team pass. |
| `discuss` | `team` | One team pass. |
| `free` | `loop` | Former consensus/infinity mode. |
| `review` | `loop` | Preserves gated review intent. |
| `verified` | `loop` | Preserves verified loop semantics. |
| `specialist` | `loop` | Uses `topology=specialist`. |

## Backend Contract

- `agent_lab.turn_modes.resolve_mode_contract()` is the single parser for room intent.
- Valid new modes are `quick`, `team`, and `loop`.
- `loop` without plan is rejected with HTTP 422 for new loop inputs.
- `team + plan` is valid and means plan-only, not execute loop.
- `verified` legacy input is allowed to keep verified loop behavior.
- No `/api/room/modes` endpoint is introduced yet; the frontend sends raw intent and the backend derives runtime fields.

Derived runtime fields include effective agents, `agent_rounds`, `runtime_turn_profile`, `consensus_mode`, `review_mode`, `topology`, and `plan_intent`.

Persisted on each room send (`run.json`: `user_mode`, `plan_intent`, `loop_topology`):

- **Plan approval gate (P1):** `approval_starts_execute_loop()` reads `plan_intent`. Only `loop` starts `verified_loop`, `goal_loop`, `mission_loop`, and `MISSION_ENABLE` on plan approve. `plan_only` (Quick/Team + plan) marks plan APPROVED and unlocks manual execute gate only. Legacy sessions without `plan_intent` keep loop-on-approve.

**Verified routing paths:**

| Source | Runtime profile | In-turn verified loop | Post-approve execute loop |
| --- | --- | --- | --- |
| UI Loop (`turn_profile=loop`) | `free` (consensus) | No | Yes (plan workflow approve) |
| Legacy API `verified` | `verified` | Yes (`maybe_handle_verified_loop_after_turn`) | Yes |
| Team + plan | `analyze` | No | No (plan-only approve) |

## Model Capability Lane

Open-source and local models are not UI modes. They are model capabilities.

`agent_lab.model_policy.ModelProfile` tracks provider, model id, agent, tool support, Inbox/MCP support, JSON envelope support, long-context support, latency tier, and cost tier. Local/open-source profiles can be Team-ready before they are Loop-ready. Loop readiness requires the model to pass tool, question-surface, and JSON envelope requirements.

**Model id lookup (P2):** `model_profile_for(agent_id)` resolves `CURSOR_MODEL` / `CODEX_MODEL` / `CLAUDE_MODEL` env overrides. Known defaults are loop-ready. Unregistered model ids are Team-ready but not Loop-ready until registered via `register_model_profile()` or `load_loop_eval_registry()` from `.agent-lab/loop_model_eval.json`.

**P3 shipped:** `GET /api/room/modes`, Team plan-approved UI hint, health `model_id`, loop budget caps (`AGENT_LAB_LOOP_MAX_*`), eval registry loader.

**P5 shipped:** runtime loop probe (`AGENT_LAB_LOOP_PROBE`, `.agent-lab/loop_probe_cache.json`), cost-tier gate (`AGENT_LAB_LOOP_MAX_COST_TIER`), composer consumes `/api/room/modes`, legacy split/infinity migration, composer question surface.

**P6 shipped:** live loop eval harness (`scripts/run_loop_model_eval.py`, `make loop-model-eval-mock|live`), composer + health cost-tier display, CI runs `integration and not live` pytest bucket.

## Question Surface

Pending Human Inbox questions are separated from the generic inbox/taskbar flow:

- Question items appear as a composer-adjacent decision surface above the composer.
- Generic Human Inbox pending states exclude question items.
- The taskbar pending hint excludes question items.

This avoids focus-stealing prompts while keeping agent questions close to the place where the user answers.

## Implementation Notes

- Frontend visible picker is Quick / Team / Loop.
- Split and infinity remain legacy/internal concepts only.
- localStorage migration normalizes old values using the migration table above.
- Loop forces the plan toggle on in the composer.
- Team leaves the plan toggle available for plan-only collaboration.
- `scripts/smoke_room.py` baselines remain part of regression verification, with an explicit test that approved plan workflow still enters `verified_loop.status=running`.

## Verification Plan

- Backend mode contract tests cover Quick slicing, Team plan-only, Loop plan requirement, `verified -> loop`, and `specialist -> loop/topology=specialist`.
- Frontend contract tests cover Quick/Team/Loop labels, Team plan availability, and removal of Split/infinity as primary modes.
- UI tests cover Question rendering above composer and exclusion from generic Inbox/taskbar.
- Regression runs include `scripts/smoke_room.py`, focused pytest suites, `npm run build`, and `make test-fast`.

## Loop participation — Later

When an agent cannot participate in a Loop/Team turn (usage limit, rate limit, or
response stall), the current behavior is: classify it as a non-participation note
(`_non_participation_reason` in `room_agent_invoke.py`), show a calm "sat out this
turn" system message, and proceed with the remaining agents (decision: keep the
note + proceed). Timeouts are bounded by `DEFAULT_CODEX_ROOM_IDLE_TIMEOUT_SEC`
(180s) and `DEFAULT_CODEX_ROOM_TIMEOUT_SEC` (300s), both env-overridable.

Deferred (Later): **alternate-model reassignment** — automatically re-route the
missing slot to another available model instead of leaving it empty. Higher value
but higher implementation/cost complexity; revisit after the participation model
(non-blocking quorum) lands.
