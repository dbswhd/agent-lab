# Quant package refactor (shipped)

Moved `quant_*.py` → `src/agent_lab/quant/` (trading lane utility validation).

| Old | New |
|-----|-----|
| `quant_utility_validation.py` | `quant/utility_validation.py` |

Canonical import: `agent_lab.quant.utility_validation`

Related subpackage: `trading_mission/` (unchanged — quant lane orchestration).

```bash
make audit-quant-imports
make typecheck-quant-ratchet
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md).
