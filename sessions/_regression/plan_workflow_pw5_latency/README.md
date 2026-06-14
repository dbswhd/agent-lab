# Plan workflow PW5 approval latency fixture

Mock dogfood topic **PW5**: peer→refine→`HUMAN_PENDING`→`approve_plan`→`APPROVED`.

Used by:
- `scenario:plan_approve_latency` (`scripts/run_dogfood_suite.py`)
- `suite-log.example.json` aggregate demo (`plan_workflow_approval_latency_sec`, `human_minutes`)

Regenerate:

```bash
AGENT_LAB_MOCK_AGENTS=1 python scripts/run_dogfood_suite.py --mode mock \
  --only PW5 --sessions-base sessions/_regression
```
