# Plan package refactor design

Design artifact mirroring [ROOM-PACKAGE-REFACTOR-DESIGN.md](ROOM-PACKAGE-REFACTOR-DESIGN.md).

Target: move `plan_*.py` → `src/agent_lab/plan/` following the `room/` subpackage pattern.

## Scope

| Item | Count |
|------|------:|
| `plan_*.py` modules at root (before) | 20 |
| Facade | none (`plan/` package only — no `plan.py` namespace conflict) |
| Modules with dedicated tests | 15+ test files under `tests/test_plan_*.py` |

## Layout (shipped)

```
src/agent_lab/
  plan/
    __init__.py
    actions.py              # was plan_actions.py
    advance.py              # was plan_advance.py
    execute.py              # was plan_execute.py
    execute_merge.py        # was plan_execute_merge.py
    execute_verify.py       # was plan_execute_verify.py
    workflow.py             # was plan_workflow.py
    ...
```

Canonical imports: `agent_lab.plan.execute`, `agent_lab.plan.workflow`, etc.

No root shims — migration was direct (89 files rewritten). Guard:

```bash
make audit-plan-imports
# tests/test_structure_metrics.py::test_audit_plan_legacy_imports_passes
```

Migration script (one-shot, kept for reference): `scripts/migrate_plan_package.py`.

## Module map

| Old path | New path |
|----------|----------|
| `plan_actions.py` | `plan/actions.py` |
| `plan_advance.py` | `plan/advance.py` |
| `plan_execute.py` | `plan/execute.py` |
| `plan_execute_*` | `plan/execute_*` |
| `plan_paths.py` | `plan/paths.py` |
| `plan_peer_iterate.py` | `plan/peer_iterate.py` |
| `plan_peer_seats.py` | `plan/peer_seats.py` |
| `plan_pending.py` | `plan/pending.py` |
| `plan_provenance.py` | `plan/provenance.py` |
| `plan_refs.py` | `plan/refs.py` |
| `plan_sync_summary.py` | `plan/sync_summary.py` |
| `plan_workflow.py` | `plan/workflow.py` |

## Migration phases

| Phase | Action | Done when |
|-------|--------|-----------|
| **1** | Move modules + rewrite imports | `audit-plan-imports` passes ✅ |
| **2** | mypy strict ratchet on `agent_lab.plan.*` | `make typecheck-plan-ratchet` ✅ (0/0) |

## Verification gates

```bash
make structure-metrics-check
make audit-plan-imports
make typecheck-plan-ratchet
make test-fast
pytest tests/test_plan_*.py -m "not live and not integration"
```

Manual: execute dry-run + plan workflow smoke (`make smoke`).

## Reference

- Room precedent: [ROOM-PACKAGE-REFACTOR-DESIGN.md](ROOM-PACKAGE-REFACTOR-DESIGN.md)
- Structure baseline: [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md)
- Ratchet baseline: `tests/fixtures/mypy-plan-ratchet.json`
