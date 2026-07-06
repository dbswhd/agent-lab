# Example missions (N8)

교육·fork 온보딩용 **정적 fixture** 3종. `sessions/_regression/`과 동일하게 `run.json` shape만 고정하고, live 세션과 `run_diff.py`로 비교할 수 있다.

| Folder | Lifecycle 단계 | PASS when |
|--------|----------------|-----------|
| `01-quick-discuss/` | Discuss (quick) | `turns[0].mode=discuss`, execute 없음 |
| `02-plan-approved/` | Plan → Human approve | `plan_workflow.phase=APPROVED` |
| `03-mission-done/` | Mission loop 완료 | `mission_loop.phase=MISSION_DONE` + merged execution |

## 비교

```bash
python scripts/run_diff.py sessions/_examples/01-quick-discuss sessions/<your-session>
```

## Live mock 재현

[QUICKSTART.md](../../docs/QUICKSTART.md) — `make dogfood-suite-mock ONLY=S1` (quick와 유사).

Regression 전체: `AGENT_LAB_MOCK_AGENTS=1 python scripts/smoke_room.py`
