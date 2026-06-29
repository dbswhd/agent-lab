# Context package refactor (shipped)

Moved `context_*.py` → `src/agent_lab/context/`.

| Old | New |
|-----|-----|
| `context_bundle.py` | `context/bundle.py` |
| `context_limits.py` | `context/limits.py` |
| `context_layers.py` | `context/layers.py` |
| `context_meta.py` | `context/meta.py` |

Note: `room/context/` package (wave B) — constraints · peer_digest · plan_excerpt · message_trim; repo tree stays in `repo_tree_context.py`. See [STRUCTURE-REFACTOR-WAVE.md](STRUCTURE-REFACTOR-WAVE.md).

```bash
make audit-context-imports
make typecheck-context-ratchet
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md).
