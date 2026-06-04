# Room session regression baselines

`run_schema_version: 1` fields: `workflow_id`, `run_schema_version`, `plan_format_version`, `topic`, `created_at`, `agents`, `status`, `message_count`, `agent_parallel_rounds`, `turns[]`, `last_plan_update`, `last_turn`, `actions[]`, `approvals[]`, `executions[]` (execute containers empty until sprint 3 #4).

Baseline scenarios (minimal `run.json` fixtures):

| Folder | Scenario | PASS when |
|--------|----------|-----------|
| `discuss/` | 일반 discuss | `turns[]` has `mode: discuss`, no `review_mode` |
| `review-on/` | 쟁점 검토 ON | `turns[]` has `mode: discuss` + `review_mode: true` |
| `plan/` | 지금 정리 | `turns[]` has `mode: plan`, `synthesize: true` |
| `objection_blocks_execute/` | open BLOCK on plan #1 | smoke validates open BLOCK linked to `plan_action` execute gate |
| `challenge_revises_metric/` | CHALLENGE → task blocked | smoke validates open CHALLENGE linked to blocked task |
| `specialist_asymmetric_cwd/` | 분업 preset | smoke: `turn_profile: specialist` + ≥2 distinct `cwd_role` in `agent_capabilities` |
| `specialist_r2_artifact_only/` | 분업 Cursor R2 payload | `last_turn.context.agents[]` has Cursor R2 `context_mode: artifact_only` |
| `bridge_degraded_health/` | Cursor bridge degraded health | `expected_health.json` has cursor `degraded`, `failure_code`, `fallback`, `remediation` |
| `mailbox_handoff/` | MESSAGE handoff | smoke: unread `mailbox[]` row + matching `mailbox_unread[target] ≥ 1` |
| `worktree_merge_ok/` | worktree merge success | `status: merged` + worktree metadata + `merge.commit_sha` |
| `worktree_reject/` | worktree rejected | `status: rejected` on worktree execution |
| `worktree_unavailable/` | worktree isolation blocked | `blocked_isolation` + `isolation_effective: block` |
| `merge_conflict/` | merge conflict state | `status: merge_conflict`, `merge.status: conflict`, conflict files |
| `worktree_apply/` | non-git apply path | `isolation_effective: apply`, no merge metadata required |
| `snapshot_override_pending/` | Human snapshot override | `snapshot_override` pending approval by Human |
| `pre_execute_blocked/` | pre-execute gate blocked | `pre_verify.blocked: true` on blocked execution |
| `adversarial_gate_lgtm/` | adversarial gate mock LGTM | dry-run `review_required` + `adversarial_note` + `expected_badges.json` |
| `execute_verify_loop/` | LC-L3 runtime verify loop | merged worktree execution has `verify_after_merge.status: passed`, `source: mock_oracle`, `reverify_endpoint`, `verify_history`, and `oracle.verdict: pass` |

Compare live sessions against baselines:

Future fixture tickets: see `docs/EXTERNAL-REFS-TRACEABILITY.md` (`durable_completed_steps`).

```bash
python scripts/run_diff.py sessions/_regression/discuss sessions/<your-session>
```

Version mismatch prints a warning only; plan/run content diff continues as before.
