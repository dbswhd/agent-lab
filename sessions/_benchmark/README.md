# Room benchmark catalog

Recorded/mock-only fixtures for H-P2. These are offline benchmark baselines; they do not call live LLMs or require an API server.

| ID | Folder | Verifies |
|----|--------|----------|
| R1 | `analyze_1r_three_views/` | One round with three agent replies; `duplicate_speech_rate` remains below threshold. |
| R2 | `plan_now_actions/` | `plan.md` has `## 지금 실행`; plan action parser returns the expected API shape. |
| R3 | `specialist_asymmetric_cwd/` | Specialist `cwd_role` plus `last_turn.context.agents[].capability_cwd` are asymmetric across R1/R2 agents; `score_session` and weekly KPI roll this into cwd-asymmetry metrics. |
| R4 | `delegate_codex/` | Delegate metadata/artifact fixture; live call count is asserted by `tests/test_room_delegate_replay.py`. |
| R5 | `ten_turn_kpi_stub/` | Synthetic 10-turn session; `score_session` keys are present. |

**Dogfood eval (v1):** [`topics/dogfood-v1.json`](topics/dogfood-v1.json) — 26 live/mock topics; [`scripts/run_dogfood_suite.py`](../../scripts/run_dogfood_suite.py); spec [`docs/EVAL-PROGRAM.md`](../../docs/EVAL-PROGRAM.md).

Execute E scenario cross-reference:

| ID | Regression fixture |
|----|--------------------|
| E1/E6 | `sessions/_regression/worktree_merge_ok/` |
| E3 | `tests/test_plan_execute_isolation.py`, `sessions/_regression/worktree_apply/` |
| E5 | `sessions/_regression/snapshot_override_pending/` |
| E7 | `sessions/_regression/merge_conflict/` |
| E8 | `sessions/_regression/pre_execute_blocked/` |

Run:

```bash
pytest tests/test_benchmark_catalog.py tests/test_room_delegate_replay.py -q
```
