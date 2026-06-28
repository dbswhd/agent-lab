# Run package refactor (shipped)

Moved `run_*.py` → `src/agent_lab/run/` (`run.json` SSOT).

| Old | New |
|-----|-----|
| `run_meta.py` | `run/meta.py` |
| `run_schema.py` | `run/schema.py` |
| `run_control.py` | `run/control.py` |
| `run_profile.py` | `run/profile.py` |
| `run_observability.py` | `run/observability.py` |

`runner.py` (graph step runner) stays at root — different concern.

Canonical helpers: `patch_run_meta()`, `read_run_meta()`, `write_run_meta()` → `agent_lab.run.meta`

```bash
make audit-run-imports
make typecheck-run-ratchet
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md).
