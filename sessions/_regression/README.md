# Room session regression baselines

`run_schema_version: 1` fields: `workflow_id`, `run_schema_version`, `plan_format_version`, `topic`, `created_at`, `agents`, `status`, `message_count`, `agent_parallel_rounds`, `turns[]`, `last_plan_update`, `last_turn`, `actions[]`, `approvals[]`, `executions[]` (execute containers empty until sprint 3 #4).

Baseline scenarios (minimal `run.json` fixtures):

| Folder | Scenario | PASS when |
|--------|----------|-----------|
| `discuss/` | 일반 discuss | `turns[]` has `mode: discuss`, no `review_mode` |
| `review-on/` | 쟁점 검토 ON | `turns[]` has `mode: discuss` + `review_mode: true` |
| `plan/` | 지금 정리 | `turns[]` has `mode: plan`, `synthesize: true` |
| `objection_blocks_execute/` | open BLOCK on plan #1 | `objections[]` open BLOCK → dry-run **409** |
| `challenge_revises_metric/` | CHALLENGE → task blocked | open CHALLENGE + task `status: blocked` |
| `specialist_asymmetric_cwd/` | 분업 preset | `agent_capabilities` + `turn_profile: specialist` |
| `mailbox_handoff/` | MESSAGE handoff | `mailbox[]` with unread for target agent |

Compare live sessions against baselines:

```bash
python scripts/run_diff.py sessions/_regression/discuss sessions/<your-session>
```

Version mismatch prints a warning only; plan/run content diff continues as before.
