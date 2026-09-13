# Dogfood readiness packet

Status: **OPEN**
Owner: Agent Lab dogfood operator
Commit: `5677b7ea881a4bfd3c55fa57c1a97f1296d42df4`

## Evidence tiers
- mock: PASS (n=2)
  - raw: `sessions/_regression/worktree_merge_ok/run.json`
  - raw: `sessions/_regression/execute_verify_loop/run.json`
- browser: PASS (n=4)
  - raw: `docs/evidence/dogfood-readiness/browser-contract.txt`
- live: OPEN (n=0)

## Flags and cohorts
- `AGENT_LAB_MOCK_AGENTS=(unset outside pytest)`
- `AGENT_LAB_MISSION_AUTHORITY=(unset)`
- `AGENT_LAB_MISSION_DUAL_WRITE=(unset)`
- `AGENT_LAB_REPO_MAP=(unset)`
- `AGENT_LAB_COMPACT_TOOL_OUTPUT=(unset)`
- cohorts: 

## Operational gates
- F7 | OPEN | owner=Agent Lab dogfood operator | next=Collect at least 10 F7-instrumented sessions at 70% repo-map coverage and record the Human ON/OFF decision.
- N4-D3 | OPEN | owner=Agent Lab dogfood operator | next=Collect at least 10 live outcome rows for every autonomy level, including L2.
- HS-M5 | OPEN | owner=Agent Lab dogfood operator | next=Preserve one addressable pattern and one live Human-approved harness_patch merge.

No default change is authorized by this packet.
