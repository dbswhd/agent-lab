# Workspace package refactor (shipped)

Moved `workspace_*.py` → `src/agent_lab/workspace/`.

| Old | New |
|-----|-----|
| `workspace_roots.py` | `workspace/roots.py` |
| `workspace_files.py` | `workspace/files.py` |
| `workspace_md.py` | `workspace/md.py` |

API router `app/server/routers/workspace_files.py` is unchanged (HTTP layer).

```bash
make audit-workspace-imports
make typecheck-workspace-ratchet
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md).
