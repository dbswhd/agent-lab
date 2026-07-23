# M6 final retire packet

Status: **GO** (readiness declaration only -- see "GO ≠ execution" below). This packet archives redacted evidence and checksums only. No product, writer, implementer, bridge, flag, session, or journal was deleted.

The `m6-final-retire.tar.gz` archive (and `archive-manifest.json`) is a frozen 2026-07-14 snapshot and is not edited. `decision.json`, `deletion-manifest.json`, `coverage.json`, and `packet-index.json` are the live tracking copies and were resynced/revalidated on 2026-07-23.

Session/journal material is checksum-only; raw content remains in place.

## 2026-07-23 resync

- Approval model: solo-dev project. The 2026-07-14 two-person approval schema was documentation convention, not an actual org requirement -- owner confirmed a single Human approval is sufficient. `approval_required`/`approval` fields updated accordingly.
- Compatibility inventory: regenerated from current code -- 18 scoped files, **277 references** (was 275 at 2026-07-14; `docs/redesign-2026-07/m6-compatibility-consumer-allowlist-2026-07-14.json` is the live-checked source of truth, kept in sync by `tests/test_m6_consumer_inventory.py`).
- Deletion manifest: **6 candidates**, `src/agent_lab/mission/advance.py` back in scope. Its 2026-07-23 topology-router state (`mission_topology`, `action_repair_cap_override`, `consecutive_verify_passes`, and `topology_wire.py`'s escalation/de-escalation functions) is carved out via a new `m6_scope_exclusions` entry instead: migrating it to `mission/kernel.py` would only matter once the dual-write bounded cohort extends authority to plan/topology decisions, which is deliberately not in progress (owner chose Wave B/inbox authority over that track on 2026-07-14) -- building kernel scaffolding now wouldn't actually unblock this file for M6 either, since M6 needs the kernel verified as *replacing* the legacy writer, and that cutover isn't happening for topology. The file's other duplicate legacy writers remain eligible for M6 whenever that work starts. See `deletion-manifest.json` for the full note; `mission/topology_wire.py`'s module docstring carries the same pointer.
## 2026-07-23 revalidation

Full re-verification of the other 5 candidates and all 4 evidence categories the 2026-07-14 packet cited, run directly against current code:

| Category | Verdict | Evidence |
| --- | --- | --- |
| git-history drift (5 non-advance.py candidates) | DRIFTED-BUT-OK | Only `mission/tick.py` has a post-07-14 commit (2026-07-18, mission-authority inbox plumbing -- no new unmigrated legacy state, covered by the 279-reference scan + `tests/test_mission_inbox_authority.py`). `runtime/transitions.py`, `runtime/orchestration.py`, `clarity.py`, `app/server/routers/room.py` are byte-identical to 07-14. |
| bridge-flag-retire (m6_9) | STILL-VALID | `plan_write_authority_enabled`/`inbox_write_authority_enabled`/`execution_write_authority_enabled` still hardcoded `False`, fully de-registered from `FLAG_REGISTRY`. |
| duplicate-patch-stop (m6_8) | DRIFTED-BUT-OK, stronger | `human_inbox.py::append_inbox_item` now genuinely skips the legacy `run["human_inbox"]` write for cohort sessions (added 2026-07-18 -- didn't exist on 07-14; original `task-8.json` evidence covered a different, weaker mechanism). |
| wave-b-parity | STILL-VALID | `mission_dual_write_verify.py`/`mission_dual_write_journal_audit.py` re-run against current `sessions/` -- the 39 hard_mismatch / 15 missing in the full inventory match `task-7.json`'s pre-known residual baseline exactly (not new drift); duplicate=0, error=0, invalid_json=0. |
| ui-soak | STILL-VALID | `AGENT_LAB_MISSION_UI_READ_MODEL` still default-on; all 5 web read-model consumers structurally unchanged; 179 web tests pass. |

258 backend tests (`test_mission_dual_write*`, `test_mission_read_model*`, `test_human_inbox`, `test_m6_*`, `test_mission_inbox_authority`, `test_crash_recovery`, `test_run_profile`, ...) all green.

**Status moved NO-GO → GO.** None of the 5 categories surfaced a real blocker -- the two "DRIFTED" findings are both cases where reality improved on what was originally evidenced, not regressions.

## GO ≠ execution

A GO readiness declaration is not itself an authorization to delete anything. Actually removing the duplicate legacy writers from the 6 candidate files is a separate, larger implementation task -- per-file ordering, rollback strategy, and a full `make test-fast` + `python scripts/smoke_room.py` re-run after each file -- and still needs its own explicit go-ahead before any code is touched.

## 2026-07-23 correction — GO covered evidence freshness, not execution readiness

Attempting to actually design the deletion work surfaced that the 2026-07-23 revalidation above (§ "2026-07-23 revalidation") only checked whether the 07-14 evidence had regressed. It never checked `m6-precheck-retire-scope-2026-07-14.md`'s per-surface execution-readiness table -- the actual gate for what's safe to delete in each candidate, independent of Human sign-off. That table's blockers (plan/execution authority not being live) mostly still apply today. `deletion-manifest.json` now carries a full `execution_readiness` breakdown; summary:

| Surface | Status |
| --- | --- |
| plan phase write | BLOCKED -- plan authority never live, no duplicate to delete |
| inbox rows | **Resolved, but not by deletion** -- see below |
| inbox gates | N/A, additive only |
| execute FSM duplicate updates | BLOCKED -- execution authority never live |
| `mission_loop` (general) | BLOCKED -- only inbox-scoped operational status shipped, not plan/execute |
| dual-write bridges/flags | BLOCKED -- single authority only proven for inbox |
| objection BLOCK | out of M6 scope |

**Inbox rows, investigated further**: the 07-14/07-16 "row writer still required" finding was produced entirely under `OpenExecutionGate`/`AGENT_LAB_MISSION_DUAL_WRITE` (id/kind/reason only -- structurally incomplete by construction). It never tested `OpenInboxItem`/`AGENT_LAB_MISSION_AUTHORITY`, the mechanism the actually-live Wave B cohort uses, which stores the full item and already skips the legacy row write. Confirmed via `tests/test_mission_inbox_authority.py` and a fresh read-model render with zero legacy rows present. This means M6-order step 2 ("inbox decision store rich enough for UI") is effectively already satisfied for that cohort -- but `src/agent_lab/human_inbox.py` stays protected either way, so this didn't unlock a deletion.

The same investigation found a **real, live bug**: `app/server/routers/room.py::_session_has_pending_human_inbox` read `run.json["human_inbox"]` directly and always returned `False` for `AGENT_LAB_MISSION_AUTHORITY`-cohort sessions, silently breaking the SSE-disconnect grace period during `ask_human` waits. Fixed to use `inbox_items_for_folder()`; regression tests added in `tests/test_room_disconnect_inbox_guard.py` (reproduced the bug pre-fix, confirmed green post-fix).

**Net result (as of the correction above)**: no candidate file had a concretely identified, safe, executable legacy-writer deletion. `status: "GO"` was accurate as an evidence-freshness statement but should be read alongside `execution_readiness`, not as "ready to delete."

## 2026-07-23 restoration — plan + execution soft authority (Slice 1/3) re-enabled

Same day, second pass: rather than leaving `plan_phase_write`/`execute_side_effects_duplicate_fsm` blocked forever, restored the pre-retire implementations of `plan_write_authority_enabled()` and `execution_write_authority_enabled()` (`src/agent_lab/mission/dual_write.py`) -- they were fully built and dogfooded live on 2026-07-14 (ADR-001 Decisions 7/9) before commit `8ccfe2c2` hard-disabled them the same day in favor of investing in Wave B. That Wave-B-first call is unchanged and correct for **inbox** authority (`inbox_write_authority_enabled` stays permanently `False` -- superseded by the stronger `AGENT_LAB_MISSION_AUTHORITY` path). Plan and execution never had a superseding mechanism, so restoring them (rather than reinventing them) is what actually lifts their blockers.

Full detail: [m6-plan-execution-authority-restoration-2026-07-23.md](./m6-plan-execution-authority-restoration-2026-07-23.md). Summary:

- Re-registered `AGENT_LAB_MISSION_PLAN_WRITE_AUTHORITY` / `AGENT_LAB_MISSION_EXECUTION_WRITE_AUTHORITY` (default `"1"` on balanced/thorough/autonomous), gated behind `AGENT_LAB_MISSION_DUAL_WRITE` + a **non-empty** session allowlist (the current, stricter `dual_write_enabled()` semantics -- the 07-14 "empty allowlist = all sessions" shortcut does not come back).
- Proved plan authority live via **real HTTP routes** (`POST /plan/approve`, `/plan/reject`, `TestClient` against production FastAPI routes, not internal function calls): cohort session gets Mission-first commit + journal `PlanApproved`; non-cohort session stays legacy-first (`reason=cohort_not_selected`); flag-off rollback is immediate and stateless.
- Proved execution authority at the function level (`tests/test_mission_dual_write.py`); a real-HTTP-route run needs git worktree scaffolding and was left for a follow-up.
- Flipped `tests/test_mission_dual_write.py`, `tests/test_run_profile.py`, `tests/test_m6_checkpoint_bridges_flags.py` back to live-authority assertions; kept the inbox-stays-retired assertions. `.env.example`, `docs/USER-GUIDE.md`, `docs/decisions/ADR-001-production-dual-write-cutover.md` re-synced.

**What this does and doesn't mean**: `execution_readiness`'s `plan_phase_write`, `execute_side_effects_duplicate_fsm`, and `mission_loop` surfaces move from BLOCKED to "precondition satisfied (cohort)" -- authority now genuinely exists, so a duplicate write is *possible* to identify and remove. It does **not** mean a specific deletable line has been found in any candidate file yet -- that line-level audit is the next step, done below.

## 2026-07-23 final audit — no executable M6-1 deletion exists

Third pass, same day: read all 5 non-excluded candidate files end-to-end (`mission/tick.py`, `runtime/transitions.py`, `runtime/orchestration.py`, `clarity.py`, `app/server/routers/room.py`) looking for the one pattern that would make a deletion safe -- a legacy write that's provably redundant with what Mission's authority path now records for cohort sessions, mirroring `human_inbox.py::append_inbox_item`'s `mission_authority_enabled(folder)` early-skip precedent.

**Found: none.** Per file:

- **`mission/tick.py`** -- doesn't write `mission_loop`/`plan_workflow`/`human_inbox` at all; the real mutations happen in `mission/loop.py`/`mission/board.py` (out of scope), invoked here as pure scheduling decisions.
- **`runtime/transitions.py`** -- zero `patch_run_meta`/`stamp_run_meta` calls; a declarative transition table plus pure guard/read functions.
- **`runtime/orchestration.py`** -- its own write (`run["orchestration"]`) is an out-of-scope observability cache; the `mission_loop`/`plan_workflow` mutation it can trigger is drift-correction between two *legacy* fields, a concept Mission's kernel has no equivalent for -- real corrective behavior, not a redundant record.
- **`clarity.py`** -- writes `mission_loop.clarity` (CLARIFY-phase panel scores + confirmed facts). `mission/kernel.py`'s `Mission` dataclass has no clarity concept whatsoever -- this is real, irreplaceable domain data. Deleting it for cohort sessions would silently lose clarity history with nothing to reconstruct from.
- **`app/server/routers/room.py`** -- full re-audit found no other authority-bypass sites beyond the one already fixed.

This is a **structural finding, not a temporary one**. Making any of these deletable would require Mission's kernel to genuinely absorb clarity-panel data and become sole authority on both sides of the orchestration drift-check -- that's M4/M5-class kernel-expansion work (`01-mission-kernel.md`), a separate and much larger initiative, not an M6 cleanup PR.

**M6 conclusion**: the packet's evidence stays **GO** (trustworthy, fresh). Plan/execution authority is genuinely restored and cohort-proven via real HTTP routes. But after the full audit, `dual_write_bridges_flags` has nothing to follow -- there is no executable M6-1 deletion available under the current architecture. This investigation is closed for now; resuming it means scoping a new kernel-expansion initiative, not continuing under this packet.
