# Context package refactor (shipped)

Moved `context_*.py` → `src/agent_lab/context/`.

| Old | New |
|-----|-----|
| `context_bundle.py` | `context/bundle.py` |
| `context_limits.py` | `context/limits.py` |
| `context_layers.py` | `context/layers.py` |
| `context_meta.py` | `context/meta.py` |

Note: `room/context.py` is Room-specific turn assembly — unchanged.

```bash
make audit-context-imports
make typecheck-context-ratchet
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md).
