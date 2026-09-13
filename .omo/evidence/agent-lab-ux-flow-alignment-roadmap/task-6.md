# Task 6 — bounded Mission authority cohorts

Commit: `6aa861d9`  
Authority activation: none. Each real cohort expansion still requires a separately recorded Human GO.

| Scenario | Invocation | Binary observable | Artifact |
| --- | --- | --- | --- |
| Four-cell plan-only / Inbox-only / both / neither matrix | focused pytest command | all parametrized route cells 200; duplicate 409; malformed 422 | `task-6/focused-tests.txt` |
| Plan approve → MCP-first Inbox open/resolve | real-route harness | `plan_approve=200`, `inbox_open_resolve=[200,200]` | `task-6/manual-route.json` |
| Stale/duplicate idempotency | real-route harness | HTTP 409 and `duplicate_event_delta=0` | `task-6/manual-route.json` |
| Process kill/restart replay | real-route harness | distinct PIDs `48909→48974`, read-model 200, `parity_divergence=0` | `task-6/manual-route.json` |
| Real disposable worktree merge + Oracle | real-route harness | resolve 200, Oracle `pass`, reverify 200, non-empty git HEAD | `task-6/manual-route.json` |
| Dirty base worktree | real-route harness | resolve blocked with HTTP 400 | `task-6/manual-route.json` |
| Misleading success | real-route harness | HTTP 200 but Oracle `fail`; Mission remains `VERIFYING` | `task-6/manual-route.json` |
| Rollback by allowlist removal | real-route harness third process | plan route 200 through legacy-first bridge, reason `cohort_allowlist_empty` | `task-6/manual-route.json` |

Overlap decision: cohorts may overlap. Rollout remains plan-first; the same already-validated session may enter `both` only after a separate Human GO. `inbox-only` remains an independence control. Empty allowlists select no sessions, and noncohort writers remain legacy-first.
