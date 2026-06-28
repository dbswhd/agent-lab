# Agent package refactor (shipped)

Moved `agent_*.py` → `src/agent_lab/agent/` (singular — distinct from `agents/` registry).

| Old | New |
|-----|-----|
| `agent_roster.py` | `agent/roster.py` |
| `agent_health.py` | `agent/health.py` |
| `agent_envelope.py` | `agent/envelope.py` |
| `agent_permissions.py` | `agent/permissions.py` |
| … | … |

Canonical imports: `agent_lab.agent.roster`, `agent_lab.agent.health`, etc.

Module alias pattern for roster tests:

```python
from agent_lab.agent import roster as ar
```

```bash
make audit-agent-imports
make typecheck-agent-ratchet
python scripts/migrate_agent_package.py  # one-shot reference
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md).
