# Phase C2 — Mission authority full-traffic cutover — 2026-07-25

> **Claimed:** Inbox Mission authority full traffic via `AGENT_LAB_MISSION_AUTHORITY=1` + `AGENT_LAB_MISSION_AUTHORITY_SESSIONS=*` (or `__all__`) on small/balanced/thorough/autonomous profiles.  
> **Not claimed:** M6 hard-delete of legacy writers · dual-write unlimited without allowlist · HS6.

## Human gate

Phase C plan: *“Human OK for full traffic after cohort; M6 rules respected.”*  
Wave B Decision Queue live acceptance (2026-07-24) closed the cohort browser gate. This cutover is the follow-on Human OK (2026-07-25 session).

## Behavior

| Before | After |
|--------|-------|
| Authority only when session id ∈ allowlist | `*` / `__all__` → every session |
| Empty allowlist → off (fail-closed) | **unchanged** — empty still disables |
| Profiles: authority unset | small/balanced/thorough/autonomous apply `AUTHORITY=1` + `SESSIONS=*` |
| Legacy `run.json` inbox writer | Still present for non-authority / flag-off paths; **not** deleted (M6) |

Code: `src/agent_lab/mission/inbox_application.py::mission_authority_enabled`  
Tests: `tests/test_mission_inbox_authority.py::test_mission_authority_full_traffic_sentinel`

## Rollback

```bash
export AGENT_LAB_MISSION_AUTHORITY=0
# or
export AGENT_LAB_MISSION_AUTHORITY_SESSIONS=
# restart API
```

## Honesty

Full traffic ≠ retire. M6 candidate deletion and empty dual-write allowlist remain forbidden.
