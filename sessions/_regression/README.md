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
| `specialist_r2_artifact_only/` | 분업 Cursor R2 payload | `last_turn.context.agents[]` has Cursor R2 `context_mode: artifact_only` |
| `bridge_degraded_health/` | Cursor bridge degraded health | `expected_health.json` has cursor `degraded`, `failure_code`, `fallback`, `remediation` |
| `mailbox_handoff/` | MESSAGE handoff | `mailbox[]` with unread for target agent |
| `worktree_merge_ok/` | worktree merge success | `status: merged` + worktree metadata + `merge.commit_sha` |
| `worktree_reject/` | worktree rejected | `status: rejected` on worktree execution |
| `worktree_unavailable/` | worktree isolation blocked | `blocked_isolation` + `isolation_effective: block` |
| `merge_conflict/` | merge conflict state | `status: merge_conflict`, `merge.status: conflict`, conflict files |
| `worktree_apply/` | non-git apply path | `isolation_effective: apply`, no merge metadata required |
| `snapshot_override_pending/` | Human snapshot override | `snapshot_override` pending approval by Human |
| `pre_execute_blocked/` | pre-execute gate blocked | `pre_verify.blocked: true` on blocked execution |

Compare live sessions against baselines:

```bash
python scripts/run_diff.py sessions/_regression/discuss sessions/<your-session>
```

Version mismatch prints a warning only; plan/run content diff continues as before.
