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
| `execute_verify_loop/` | LC-L3 agent repair loop | Oracle FAIL triggers a Cursor/Codex repair worktree and re-merge; final execution has `repair_history`, `verify_retries` within 2, `verify_after_merge.status: passed`, and `oracle.verdict: pass` |
| `durable_completed_steps/` | CENT-durable resume snapshot | `completed_steps[]` with turn/round/agent key; partial turn with `succeeded_agents` |
| `goal_loop_achieved/` | LC-L5 session goal achieved | mock Oracle PASS + `goal_loop.status: achieved` |
| `mission_loop_execute_queue/` | Mission Loop execute queue | `mission_loop.enabled` + `phase: EXECUTE_QUEUE` + `plan_gate.status: ok` + `verified_loop.loop_goal` |
| `mission_loop_paused/` | Mission Loop pause/resume | `phase: MISSION_PAUSED` + `pause_reason` + `last_partial.resume_phase` |
| `mission_loop_circuit_breaker/` | Mission Loop circuit breaker | `circuit_breaker: true` + `discuss_recovery.pending` |
| `envelope_consensus_endorse/` | Envelope consensus (no legacy phrase) | `consensus.status: reached` + `communicate_meta.legacy_endorse_count: 0` |
| `mission_loop_dogfood_ok/` | Mission dogfood KPI golden | `MISSION_DONE` + merged execution + notepad chars ≥200 |
| `evidence_gates_merged_ok/` | MB-3 five evidence gates | merged execution + 5 gates + `oracle_verdict: pass` + `plan_gate.status: ok` |
| `evidence_ledger_stream/` | MB-4 evidence ledger | `evidence.jsonl` ≥2 lines + `evidence_ledger.entry_count` |
| `external_handoff_attached/` | MB-8 external handoff | execution `external_handoff` with required GJC keys |
| `wisdom_index_built/` | MB-10 wisdom index | `wisdom_index.json` + companion `evidence.jsonl` + mission `wisdom_refs` |

Compare live sessions against baselines:

Future fixture tickets: see `docs/EXTERNAL-REFS-TRACEABILITY.md` (MD-PROJECT, MD-PLATFORM).

```bash
python scripts/run_diff.py sessions/_regression/discuss sessions/<your-session>
```

Version mismatch prints a warning only; plan/run content diff continues as before.
