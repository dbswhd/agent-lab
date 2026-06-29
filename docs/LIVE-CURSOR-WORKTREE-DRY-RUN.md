# Live Cursor worktree dry-run (M0 Go/No-Go)

See [OPS-RUNBOOK.md](OPS-RUNBOOK.md) Tier B for when to run this check and how it fits with `make verify-ops`. Tier C approve/merge coverage is in [LIVE-MERGE-OPERATOR.md](LIVE-MERGE-OPERATOR.md).

Offline pytest proves worktree wiring with a mocked `cursor_agent.respond`. This runbook performs **one real** Cursor SDK call in an **isolated disposable git repo** so `main` in that repo stays clean until merge (here we **reject** after dry-run, so no merge).

## Prerequisites

| Requirement | Check |
|-------------|--------|
| `pip install -e ".[cursor]"` | `python -c "import cursor_sdk"` |
| `CURSOR_API_KEY` | `~/.agent-lab/.env` or repo `.env` (never commit) |
| Bridge | `CURSOR_SDK_BRIDGE_BIN` auto-launch or external `CURSOR_SDK_BRIDGE_URL` |
| Clean git | Script uses a **temp repo**, not agent-lab `main` |

## Run (operator)

```bash
cd /path/to/agent-lab
export AGENT_LAB_RUN_LIVE=1
make verify-ops-live
# lower-level command:
make live-worktree-dry-run
# or
python scripts/live_cursor_worktree_dry_run.py --write /tmp/live-m0-report.json
```

Expected stdout (shape):

```
Live Cursor worktree dry-run: GO
  preflight ready: True
  isolation_worktree: OK
  main_clean_after_dry_run: OK
  cwd_is_worktree_root: OK
  worktree_removed_after_reject: OK
  ...
```

Exit codes: `0` = Go, `2` = No-Go, `3` = skipped (no key/bridge), `1` = guard or usage.

## What is verified

| Check | Meaning |
|-------|---------|
| `isolation_worktree` | `execution.isolation_effective == worktree` |
| `main_clean_after_dry_run` | base branch porcelain empty after Cursor run |
| `cwd_is_worktree_root` | worktree path is its own git root |
| `worktree_removed_after_reject` | reject discards worktree |
| `main_clean_after_reject` | base still clean after reject |

Agent may or may not edit `src/spike.txt`; Go/No-Go is **mechanical isolation**, not LLM quality.

## Last verified (repo maintainer)

| Date | Result | Notes |
|------|--------|-------|
| 2026-06-03 | **GO** | `AGENT_LAB_RUN_LIVE=1`, bridge `auto`, ~25s, all mechanical checks OK |

## CI policy

- **Not** run in GitHub Actions (no secrets / no bridge).
- Mock coverage: `tests/test_live_execute_spike.py` (default `pytest`).
- Optional local: `AGENT_LAB_RUN_LIVE=1 pytest tests/test_live_execute_spike.py -m live`.

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Exit 1 guard | Export `AGENT_LAB_RUN_LIVE=1` |
| Exit 3 / preflight not ready | Health panel **재연결** or start bridge; see `STABILITY.md` bridge degraded |
| `no_go` + main dirty | File bug — worktree path must not be agent-lab repo root |
| Slow / timeout | Normal for live agent; retry with `--keep-artifacts` and inspect `work-dir/repo` |

## Related

- Design: `docs/EXECUTE-WORKTREE-REFORM.md` §11 M0
- Code: `scripts/soak/live_execute_spike.py` (shim: `src/agent_lab/live_execute_spike.py`), `scripts/live_cursor_worktree_dry_run.py`
- Tier C merge: `docs/LIVE-MERGE-OPERATOR.md`, `scripts/live_cursor_worktree_merge_run.py`
