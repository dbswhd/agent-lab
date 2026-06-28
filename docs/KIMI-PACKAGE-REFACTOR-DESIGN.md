# Kimi package refactor (shipped)

Moved `kimi_*.py` → `src/agent_lab/kimi/`.

| Old | New |
|-----|-----|
| `kimi_provider.py` | `kimi/provider.py` |
| `kimi_control_client.py` | `kimi/control_client.py` |
| `kimi_daimon_supervisor.py` | `kimi/daimon_supervisor.py` |
| `kimi_work_*.py` | `kimi/work_*.py` |

Canonical imports: `agent_lab.kimi.provider`, `agent_lab.kimi.work_provider`, etc.

Registry wiring:

```python
from agent_lab.kimi import provider as kimi_provider, work_provider as kimi_work_provider
```

```bash
make audit-kimi-imports
python scripts/migrate_kimi_package.py  # one-shot reference
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md).
