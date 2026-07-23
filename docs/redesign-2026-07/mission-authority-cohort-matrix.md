# Mission authority bounded-cohort matrix

Status: validation contract only. No production cohort is activated by this document or its harness.

Plan and execution authority share `AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS`; Inbox authority independently uses `AGENT_LAB_MISSION_AUTHORITY_SESSIONS`.

| Cohort cell | Dual-write allowlist | Inbox-authority allowlist | Plan / execution writer | Inbox writer |
| --- | --- | --- | --- | --- |
| plan-only | session present | absent | Mission commit, legacy side effects retained | legacy-first |
| Inbox-only | absent | session present | legacy-first | Mission journal |
| both | session present | session present | Mission commit, legacy side effects retained | Mission journal |
| neither | absent | absent | legacy-first | legacy-first |

The allowlists may overlap. Rollout is plan-first: validate plan approve/reject in the dual-write cohort, then—after a separate recorded Human GO—add a validated session to the Inbox allowlist so it enters `both`; only after another Human GO may execution/merge/Oracle authority be exercised for that bounded dual-write cohort. An `inbox-only` cell remains a control proving the allowlists are independent.

Empty allowlists select no sessions. Removing a session from either allowlist immediately returns that surface to legacy-first behavior; flags alone never select full traffic. Noncohort behavior and global defaults remain unchanged.

`scripts/mission_authority_cohort_matrix.py` validates all four cells through production routes. `scripts/mission_authority_real_route_harness.py` uses disposable sessions and git repositories to validate process restart, stale/duplicate and malformed responses, dirty-worktree rejection, real merge/Oracle side effects, misleading HTTP success with Oracle FAIL, and rollback by allowlist removal. Harness output is evidence, not Human GO and not authority activation.
