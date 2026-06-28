# Session package refactor (shipped)

Moved `session.py` + `session_*.py` → `src/agent_lab/session/`.

| Old | New |
|-----|-----|
| `session.py` | `session/__init__.py` (slugify, session_dir, save_session + paths re-exports) |
| `session_paths.py` | `session/paths.py` |
| `session_guidance.py` | `session/guidance.py` |
| `session_clarifier.py` | `session/clarifier.py` |
| `session_setup.py` | `session/setup.py` |
| `session_score.py` | `session/score.py` |
| `session_score_weekly.py` | `session/score_weekly.py` |
| `session_plugin_runtime.py` | `session/plugin_runtime.py` |

Canonical imports: `agent_lab.session`, `agent_lab.session.paths`, etc.

```bash
make audit-session-imports
python scripts/migrate_session_package.py  # one-shot reference
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md).
