# M6 Slice 1/3 soft-authority restoration — 2026-07-23

> **Role:** evidence for `deletion-manifest.json`'s `execution_readiness.plan_phase_write` and
> `.execute_side_effects_duplicate_fsm` moving from BLOCKED to cohort-scoped SATISFIED.
> **Related:** [ADR-001](../../decisions/ADR-001-production-dual-write-cutover.md) (Status updated 2026-07-23) ·
> [m6-precheck-retire-scope-2026-07-14.md](./m6-precheck-retire-scope-2026-07-14.md) (the original blocker
> this restoration lifts) · [dual-write-retire-slice-plan-soft-2026-07-14.md](./dual-write-retire-slice-plan-soft-2026-07-14.md)
> (the original 2026-07-14 slice this un-retires).

## What changed

Commit `8ccfe2c2` (2026-07-14) hard-disabled `plan_write_authority_enabled()` / `execution_write_authority_enabled()`
(`return False`, unconditionally) and de-registered their env vars, in favor of investing in Wave B
(inbox authority + journal-first read-model). That decision is unchanged and correct for *inbox*
(`inbox_write_authority_enabled` stays hardcoded `False` permanently — superseded by the stronger
`AGENT_LAB_MISSION_AUTHORITY` path). But it also blocked `mission/advance.py`'s M6 candidacy for
plan/execute, since with authority permanently off there was no "duplicate legacy writer" to ever
retire in the first place.

2026-07-23: restored the pre-retire implementations of `plan_write_authority_enabled()` and
`execution_write_authority_enabled()` verbatim (`src/agent_lab/mission/dual_write.py`), re-registered
their flags (`AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY`, `AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY`,
default `"1"` on balanced/thorough/autonomous), and flipped the corresponding tests back to asserting
live behavior (`tests/test_mission_dual_write.py`, `tests/test_run_profile.py`,
`tests/test_m6_checkpoint_bridges_flags.py`).

**Important semantic difference from 2026-07-14**: `dual_write_enabled()` was also changed in the same
retiring commit, from "empty allowlist = all sessions" to "empty allowlist disables the bridge
entirely." Authority now inherits that stricter behavior — a session must be explicitly named in
`AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS` for authority to apply. Non-cohort sessions (the ~100% default)
are completely unaffected either way.

## Real production-route evidence (not just internal function calls)

`scripts/mission_plan_execution_authority_route_2026-07-23.py` exercises the actual FastAPI routes
(`POST /api/sessions/{id}/plan/approve`, `/plan/reject`) via `TestClient` against a scratch sessions
directory — same harness pattern as `scripts/mission_ui_read_model_cohort.py`. Run:

```bash
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/mission_plan_execution_authority_route_2026-07-23.py --sessions <scratch-dir>
```

Result (2026-07-23, `pass: true`):

| Scenario | Result |
| --- | --- |
| Approve, session in `DUAL_WRITE_SESSIONS`, authority on | `200`, phase `APPROVED`, `mirrored=true`, journal file created with `PlanApproved` |
| Reject → `REFINE`, authority on | `200`, phase `REFINE`, `mirrored=true` |
| Approve, session NOT in the allowlist (authority + dual-write both on) | `200`, phase `APPROVED` via **legacy-first** path, `mirrored=false`, `reason=cohort_not_selected` — proves non-cohort sessions are unaffected |
| Approve, `PLAN_WRITE_AUTHORITY` unset (rollback), session still allowlisted | `200`, phase `APPROVED` via legacy-first + mirror (`operation=plan_approve`), not the authority commit path — proves flag-off rollback is immediate and stateless |

## Execution authority (Slice 3) — scope note

Execution authority (`commit_execution_transition` fail-closing `/execute/resolve`, `/execute/merge/confirm`,
`/execute/reverify`) is restored identically at the function level and covered by
`tests/test_mission_dual_write.py::test_execution_write_authority_commit_approve` /
`::test_execution_write_authority_reject_stays_legacy_only` (both green, 2026-07-23). A real-HTTP-route
run for execution needs actual git worktree scaffolding (see the retired `scripts/mission_dual_write_route_cohort.py`,
which itself needs updating for the new non-empty-allowlist semantics before reuse) — that is a
separate, larger verification exercise, intentionally out of scope for this restoration.

## Test suites re-verified green (2026-07-23)

```bash
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/pytest tests/test_mission_dual_write.py tests/test_run_profile.py \
  tests/test_m6_checkpoint_bridges_flags.py tests/test_m6_checkpoint_duplicate_patches.py \
  tests/test_runtime_flags_registry.py tests/test_m6_consumer_inventory.py tests/test_m6_final_retire_packet.py \
  tests/test_room_disconnect_inbox_guard.py tests/test_mission_inbox_authority.py tests/test_dual_write_observability.py -q
# 118 passed
```

Full `make test-fast` + `python scripts/smoke_room.py` re-run after this restoration; see the M6
final-retire packet's `execution_readiness` for the updated per-surface status.
