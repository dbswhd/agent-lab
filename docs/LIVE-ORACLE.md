# Live Oracle — execute verify + session goal

Mock-first by default. Mission Loop and execute repair loops trust **independent** verification — live mode is opt-in.

## Environment

| Variable | Default | Effect |
|----------|---------|--------|
| `AGENT_LAB_ORACLE_LIVE` | off | Live Claude oracle for **execute** verify (`plan_execute_merge.oracle_verify`) |
| `AGENT_LAB_GOAL_ORACLE_LIVE` | off | Live oracle for **session goal** checks only |
| either `ORACLE_LIVE=1` | — | Enables **both** execute and goal live oracles |

CI and `sessions/_regression/*` never require live keys.

## Response format (live + mock)

Oracles return structured text parsed by `oracle_core.parse_oracle_response`:

```text
VERDICT: pass|fail
REASON: one or two sentences
EVIDENCE:
- bullet citing files, transcript lines, or commands checked
```

Legacy `PASS:` / `FAIL:` prefixes still parse.

## Evidence bundle (execute)

Live and mock execute oracles receive:

- Merged file snippets (cap 5 files × 600 chars)
- Suggested commands parsed from plan `검증:` / backticks (`make test`, `pytest`, …)
- Mission notepad tail (`verification.md`, `learnings.md`) when present

Results persist on `execution.oracle`:

- `verdict`, `detail`, `evidence[]`, `source`, `prompt_version`, `checked_paths`

`verify_after_merge.source` is `mock_oracle` or `live_oracle`.

## Mission Loop wiring

After merge verify, `mission_loop.on_verify_result` appends oracle `detail` + `evidence` bullets to `verification.md`.

## Dogfood / regression

```bash
make test -k oracle
python scripts/mission_dogfood_report.py sessions/_regression/mission_loop_dogfood_ok
```

Golden execute verify: `sessions/_regression/execute_verify_loop/`.

## Related

- [GOAL-LOOP.md](./GOAL-LOOP.md) — session goal Oracle
- [MISSION-DOGFOOD.md](./MISSION-DOGFOOD.md) — mission KPI checklist
- `src/agent_lab/oracle_core.py` — prompts + parsing SSOT
