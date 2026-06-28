# Mission package refactor (shipped)

Moved `mission_*.py` → `src/agent_lab/mission/`.

| Old | New |
|-----|-----|
| `mission_loop.py` | `mission/loop.py` |
| `mission_advance.py` | `mission/advance.py` |
| `mission_board.py` | `mission/board.py` |
| `mission_notepad.py` | `mission/notepad.py` |
| `mission_scheduler.py` | `mission/scheduler.py` |
| `mission_templates.py` | `mission/templates.py` |
| `mission_tick.py` | `mission/tick.py` |

Canonical imports: `agent_lab.mission.loop`, `agent_lab.mission.advance`, etc.

Note: `trading_mission/` is a separate subpackage (quant lane) — unchanged.

```bash
make audit-mission-imports
python scripts/migrate_mission_package.py  # one-shot reference
```

See [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md).
