# Structure metrics baseline

Reproducible indicators for `src/agent_lab/` flattening and frontend component size.
Use these before and after each refactor wave to confirm scope and catch accidental drift.

## Run

```bash
make structure-metrics          # human-readable summary
make structure-metrics-check    # fail on baseline drift (CI-friendly)
make audit-room-imports         # fail on legacy agent_lab.room_* imports
make audit-plan-imports
make audit-session-imports
make audit-kimi-imports
make audit-mission-imports
make audit-agent-imports
make audit-quant-imports
make audit-wisdom-imports
make audit-inbox-imports
make audit-context-imports
make audit-run-imports
make audit-workspace-imports
make audit-research-imports
make typecheck-room-ratchet     # strict mypy ratchet for src/agent_lab/room
make typecheck-plan-ratchet     # strict mypy ratchet for src/agent_lab/plan
make typecheck-session-ratchet  # strict mypy ratchet for src/agent_lab/session
make typecheck-kimi-ratchet     # strict mypy ratchet for src/agent_lab/kimi
make typecheck-mission-ratchet  # strict mypy ratchet for src/agent_lab/mission
make typecheck-agent-ratchet    # strict mypy ratchet for src/agent_lab/agent
make typecheck-quant-ratchet    # strict mypy ratchet for src/agent_lab/quant
make typecheck-wisdom-ratchet   # strict mypy ratchet for src/agent_lab/wisdom
make typecheck-inbox-ratchet    # strict mypy ratchet for src/agent_lab/inbox
make typecheck-context-ratchet  # strict mypy ratchet for src/agent_lab/context
make typecheck-run-ratchet      # strict mypy ratchet for src/agent_lab/run
make typecheck-workspace-ratchet  # strict mypy ratchet for src/agent_lab/workspace
make typecheck-research-ratchet   # strict mypy ratchet for src/agent_lab/research
python scripts/mypy_room_ratchet.py --print
python scripts/mypy_plan_ratchet.py --print
python scripts/room_import_graph.py
python scripts/audit_room_legacy_imports.py
python scripts/audit_plan_legacy_imports.py
```

## Current snapshot (2026-06-28)

| Metric | Value |
|--------|------:|
| Root `src/agent_lab/*.py` modules | 116 |
| Existing subpackages | … **`workspace`**, **`research`**, … (see baseline JSON) |
| tracked prefix modules at root | **0** |
| Tracked `__pycache__` / `.pyc` | **0** |
| Makefile lines / targets | see `structure-metrics-baseline.json` |
| `RoomChat.tsx` lines | 4467 |
| `PlanExecutePanel.tsx` lines | 1567 |

Baseline JSON: `tests/fixtures/structure-metrics-baseline.json`.

Update the baseline intentionally after a refactor wave:

```bash
.venv/bin/python scripts/structure_metrics.py --write-baseline
```

## Package ratchets

| Package | Strict overrides | Ratchet script | Baseline |
|---------|------------------|----------------|----------|
| `agent_lab.room.*` | `pyproject.toml` | `scripts/mypy_room_ratchet.py` | `tests/fixtures/mypy-room-ratchet.json` (0/0) |
| `agent_lab.plan.*` | `pyproject.toml` | `scripts/mypy_plan_ratchet.py` | `tests/fixtures/mypy-plan-ratchet.json` (0/0) |

| `agent_lab.session.*` | `pyproject.toml` | `scripts/mypy_session_ratchet.py` | `tests/fixtures/mypy-session-ratchet.json` (0/0) |
| `agent_lab.kimi.*` | `pyproject.toml` | `scripts/mypy_kimi_ratchet.py` | `tests/fixtures/mypy-kimi-ratchet.json` (0/0) |
| `agent_lab.mission.*` | `pyproject.toml` | `scripts/mypy_mission_ratchet.py` | `tests/fixtures/mypy-mission-ratchet.json` (0/0) |
| `agent_lab.agent.*` | `pyproject.toml` | `scripts/mypy_agent_ratchet.py` | `tests/fixtures/mypy-agent-ratchet.json` (0/0) |
| `agent_lab.quant.*` | `pyproject.toml` | `scripts/mypy_quant_ratchet.py` | `tests/fixtures/mypy-quant-ratchet.json` (0/0) |
| `agent_lab.wisdom.*` | `pyproject.toml` | `scripts/mypy_wisdom_ratchet.py` | `tests/fixtures/mypy-wisdom-ratchet.json` (0/0) |
| `agent_lab.inbox.*` | `pyproject.toml` | `scripts/mypy_inbox_ratchet.py` | `tests/fixtures/mypy-inbox-ratchet.json` (0/0) |
| `agent_lab.context.*` | `pyproject.toml` | `scripts/mypy_context_ratchet.py` | `tests/fixtures/mypy-context-ratchet.json` (0/0) |
| `agent_lab.run.*` | `pyproject.toml` | `scripts/mypy_run_ratchet.py` | `tests/fixtures/mypy-run-ratchet.json` (0/0) |
| `agent_lab.workspace.*` | `pyproject.toml` | `scripts/mypy_workspace_ratchet.py` | `tests/fixtures/mypy-workspace-ratchet.json` (0/0) |
| `agent_lab.research.*` | `pyproject.toml` | `scripts/mypy_research_ratchet.py` | `tests/fixtures/mypy-research-ratchet.json` (0/0) |

Root mypy ratchet excludes all packaged subdirs under `src/agent_lab/` (see `tests/fixtures/mypy-ratchet.json` `exclude_prefixes`).

## `__pycache__` — not tracked repo debt

Earlier reviews flagged hundreds of local `__pycache__/` directories. Those are **ignored by `.gitignore`** and do not appear in git history:

```bash
git ls-files '*__pycache__*' '*.pyc'   # expect 0
```

**Do not** run `git rm -r --cached` on `__pycache__` — there is nothing to untrack.
Local cleanup when needed:

```bash
find . -type d -name __pycache__ -prune -exec rm -rf {} +
```

Completion criterion: keep `tracked_pycache_files == 0` (enforced by `make structure-metrics-check`).

## Makefile scope

The root Makefile shares ops/trading/quant targets with core dev targets (`install`, `test-fast`, `lint`).
Domain split is deferred; this baseline records the starting point.

## Large frontend components

Tracked TSX files ≥500 lines (top entries) — see `large_tsx_files` in baseline JSON.

## F9 hot-path Python ratchet

Pinned in `tests/fixtures/structure-metrics-baseline.json` → `hot_path_py_files`:

| Lines | Path |
|------:|------|
| 1691 | `src/agent_lab/plan/execute.py` |
| 1281 | `src/agent_lab/plan/workflow.py` |
| 1084 | `src/agent_lab/room/turn_flow.py` |

`make structure-metrics-check` fails on any LOC drift (growth **or** shrink without `--write-baseline`).
After intentional refactor extraction, lower the cap:

```bash
.venv/bin/python scripts/structure_metrics.py --write-baseline
```

Legacy snapshot (2026-06-28) for comparison:

| Lines | Path |
|------:|------|
| 4467 | `web/src/components/RoomChat.tsx` |
| 1567 | `web/src/components/PlanExecutePanel.tsx` |

Frontend extraction is a **separate wave** from Python package moves. Active execute plan: [STRUCTURE-REFACTOR-WAVE.md](STRUCTURE-REFACTOR-WAVE.md).

## Related

- [ROOM-PACKAGE-REFACTOR-DESIGN.md](ROOM-PACKAGE-REFACTOR-DESIGN.md)
- [PLAN-PACKAGE-REFACTOR-DESIGN.md](PLAN-PACKAGE-REFACTOR-DESIGN.md)
- [SESSION-PACKAGE-REFACTOR-DESIGN.md](SESSION-PACKAGE-REFACTOR-DESIGN.md)
- [MISSION-PACKAGE-REFACTOR-DESIGN.md](MISSION-PACKAGE-REFACTOR-DESIGN.md)
- [AGENT-PACKAGE-REFACTOR-DESIGN.md](AGENT-PACKAGE-REFACTOR-DESIGN.md)
- [QUANT-PACKAGE-REFACTOR-DESIGN.md](QUANT-PACKAGE-REFACTOR-DESIGN.md)
- [WISDOM-PACKAGE-REFACTOR-DESIGN.md](WISDOM-PACKAGE-REFACTOR-DESIGN.md)
- [INBOX-PACKAGE-REFACTOR-DESIGN.md](INBOX-PACKAGE-REFACTOR-DESIGN.md)
- [CONTEXT-PACKAGE-REFACTOR-DESIGN.md](CONTEXT-PACKAGE-REFACTOR-DESIGN.md)
- [RUN-PACKAGE-REFACTOR-DESIGN.md](RUN-PACKAGE-REFACTOR-DESIGN.md)
- [WORKSPACE-PACKAGE-REFACTOR-DESIGN.md](WORKSPACE-PACKAGE-REFACTOR-DESIGN.md)
- [RESEARCH-PACKAGE-REFACTOR-DESIGN.md](RESEARCH-PACKAGE-REFACTOR-DESIGN.md)
