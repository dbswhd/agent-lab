# Revision (stage_n 2) — Structural Debt Decomposition (folds Architect A1/A2/A3 + Critic gating fixes)

> Supersedes stage-01-planner. Orchestrator-direct revision (subagent dispatch defect documented: role-lane subagents return 0B; orchestrator runs Planner/Architect/Critic lanes directly and persists via `gjc ralplan --write`). Option A (façade-preserving leaf extraction) retained — risk posture unchanged. Three gating fixes applied.

## Fix 1 (Critic #1 / Architect A2) — honest scope: module extraction vs function decomposition
Line-count alone is gameable. The plan now distinguishes two delivery scopes and adds **Phase 3** for the giant functions, with a scope-discriminating AC.

- **Phase 1 / Phase 2 = module-level extraction** (helper clusters -> leaf modules). Delivers the navigability/context-load win for everything *except* the two giants.
- **Phase 3 = function-level decomposition of the two giants** (`run_dry_run` ~500, `resolve_execution` ~300), split into named **private step-helpers within `plan_execute.py`** (NOT new public functions — no signature/API change). Each helper is a pure extract-method move of a cohesive block (e.g. `_dry_run_preflight`, `_dry_run_snapshot_diff`, `_dry_run_emit_execution`; `_resolve_apply_vote`, `_resolve_merge_path`, `_resolve_finalize`). Behavior-preserving; the public function bodies become orchestration of the step-helpers.
- Phase 3 is **independently shippable and may be deferred**: if the user wants the fast win first, Phases 1–2 ship alone and Phase 3 is the registered follow-up. The plan does not *claim* the giants are decomposed unless Phase 3 runs.

## Fix 2 (Critic #2 / Architect A1) — migrate-by-default for the countable external movers
Re-export is no longer the default. Enumerated external import sites for symbols that change module home, to be migrated via `lsp rename`/`references` (resolves function-local lazy imports that grep misses):

| Moved symbol | New home | External import sites to migrate |
|---|---|---|
| `mission_notepad_dir` | `mission_notepad.py` | `src/agent_lab/evidence_ledger.py` (top-level import) |
| `build_mission_wisdom_block` | `mission_notepad.py` | `src/agent_lab/runtime/context.py` (local import, alias `_build`) |
| `inject_wisdom_into_prompt` | `mission_notepad.py` | `src/agent_lab/runtime/context.py` (local import) |
| `maybe_advance_mission`, `mission_autorun_enabled` | `mission_advance.py` | `src/agent_lab/mission_tick.py` (local import block) |

- These ≤4 files are migrated to the new module path. **`plan_execute.py` public entrypoints do NOT move** — they stay in core, so Phase 1 has zero external-import churn.
- **Re-export is reserved** only for a moved symbol whose caller set is large or cannot be fully enumerated by `lsp references`. (Pre-flight: run `lsp references` on each mover; if it returns a small closed set, migrate; if large/open, re-export with a `# back-compat re-export` comment.)
- Net effect: the final import graph is honest (paths reflect true homes) without raising breakage risk, because LSP migration is deterministic and the full fast lane backstops.

## Fix 3 (Critic #3 / Architect A3) — proof-bearing constant single-ownership
AC6 upgraded: every moved module-level constant has **exactly one definition site**; re-export lines reference, never redefine. Verified by grep-proof captured in the QA artifact:
- `git grep -nE '^(PENDING_STATUS|MAX_DIFF_CHARS|MAX_VERIFY_RETRIES) =' src/` -> each exactly one hit.
- `git grep -nE '^(MISSION_WISDOM_INJECT_CAP|MISSION_NOTEPAD_FILES) =' src/` -> each exactly one hit.
- `_CANCELLABLE_EXECUTION_STATUSES`, `_OPEN_EXECUTION_STATUSES`, `_NOTEPAD_HEADERS`, `_NOTEPAD_READ_ORDER`, `_ROLLBACK_RESUME_PHASES`, `_STRUCTURAL_VERIFY_MARKERS` -> each exactly one definition.

## Revised Acceptance Criteria (consolidated)
- **AC1** (refined): `plan_execute.py` and `mission_loop.py` each <= ~900 lines after their module-extraction phase; new leaf modules each <= ~450 lines.
- **AC2**: external public symbols importable from their *correct* path post-migration. Probe (post Phase 1/2):
  `python -c "from agent_lab.plan_execute import run_dry_run, resolve_execution, confirm_merge_execution, abort_merge_execution, list_plan_actions, execution_allows_task_complete, PENDING_STATUS; from agent_lab.mission_loop import get_mission_loop, public_mission_payload, evaluate_plan_gate, after_plan_scribe, enable_mission_loop; from agent_lab.mission_notepad import mission_notepad_dir, build_mission_wisdom_block, inject_wisdom_into_prompt; from agent_lab.mission_advance import maybe_advance_mission, mission_autorun_enabled"` exits 0. (Plan_execute publics unchanged path; mission notepad/advance from new homes since callers are migrated.)
- **AC3**: `app.server.main:app` imports cleanly.
- **AC4**: `make test-fast` -> baseline pass count (~1101), 0 failures (known 2 pre-existing integration env failures excluded; not in fast lane).
- **AC5**: `ruff check src/agent_lab` clean; `mypy src/agent_lab` no new errors vs baseline.
- **AC6** (proof-bearing): single definition home per moved constant — grep-proof above in QA artifact.
- **AC7**: no new import cycle — import smoke of all touched + new modules.
- **AC8** (new — anti-gaming scope discriminator): the run's deliverable explicitly states which scope shipped — "module extraction (Phases 1–2)" and/or "function decomposition (Phase 3)". A green AC1 line-count alone does NOT constitute Phase 3; Phase 3 requires the named step-helpers to exist and the giants to be reduced to orchestration bodies.

## Unchanged from stage-01
Principles (1–5), Decision Drivers (1–3), Options A/B/C (A chosen), pre-mortem (3 scenarios), expanded test plan (unit/integration/e2e/observability), and the decomposition map (status/verify/prompts; notepad/advance) all stand. Out-of-scope items unchanged (app/server mypy coverage; public-API signature changes; any logic/perf change).
