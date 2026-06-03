# Agent Lab Ops Runbook

Manual operations checks are split into tiers so CI-safe regression checks and live Cursor SDK checks stay separate.

## Tier A — PR and weekly baseline

Use Tier A for every PR before merge and for weekly local checks.

```bash
make verify-ops
```

This runs regression CI, checks execute worktree orphans, writes weekly JSON/Markdown artifacts, and prints:

```text
Ops report: sessions/_reports/weekly-YYYY-MM-DD.md
```

The weekly Markdown includes **Last live checks** from the newest `live-worktree-*.json` and `live-merge-*.json` files in `sessions/_reports/`.

Useful variants:

| Command | Use |
|---------|-----|
| `make verify-ops REPORT=0` | Fast CI-safe check without writing a weekly artifact. |
| `make verify-ops INCLUDE_FIXTURES=1 DAYS=30` | Offline demo report that includes regression fixtures. |
| `STRICT=1 make verify-ops INCLUDE_FIXTURES=1` | Fail with exit 2 when M4 milestones fail. |

## Tier B — live worktree verification

Use Tier B monthly, after execute/worktree changes, or after Cursor bridge updates. It performs one real Cursor SDK dry-run in a disposable git repo and rejects the execution, so no merge occurs.

Precondition: Tier A is green.

```bash
AGENT_LAB_RUN_LIVE=1 make verify-ops-live
```

The target runs Tier A preflight with `REPORT=0` unless `SKIP_PREFLIGHT=1` is set, then writes:

```text
Live ops report: sessions/_reports/live-worktree-YYYY-MM-DD.json (GO)
```

Use this only on a machine with `CURSOR_API_KEY` and a working bridge. It is intentionally not part of GitHub Actions.

```bash
AGENT_LAB_RUN_LIVE=1 SKIP_PREFLIGHT=1 make verify-ops-live
```

### Go / No-Go

| Check | GO means |
|-------|----------|
| Preflight | Cursor SDK/bridge is ready or the live script records an intentional skip. |
| Main clean | The disposable base repo stays clean after dry-run and reject. |
| Worktree isolation | Dry-run executes from the isolated worktree git root. |
| Worktree discard | Reject removes the execution worktree. |

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | GO |
| 1 | Usage or missing `AGENT_LAB_RUN_LIVE=1` guard |
| 2 | NO_GO |
| 3 | SKIPPED, usually missing key/bridge or `AGENT_LAB_SKIP_LIVE=1` |

## Tier C — live merge

Use Tier C after Tier B returns GO, after execute/merge code changes, or once per branch cut. It runs one live dry-run in the same kind of disposable git repo, approves the pending execution, and verifies the merge commit on the disposable base branch.

```bash
AGENT_LAB_RUN_LIVE=1 make verify-ops-live-merge
```

The target runs Tier A preflight with `REPORT=0` unless `SKIP_PREFLIGHT=1` is set, then writes:

```text
Live merge ops report: sessions/_reports/live-merge-YYYY-MM-DD.json (GO)
```

Rollback instructions and the operator prompt are in [LIVE-MERGE-OPERATOR.md](LIVE-MERGE-OPERATOR.md).

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Bridge degraded | Check `/api/health?probe_bridge=true`; use the health panel reconnect action. |
| Exit 1 | Export `AGENT_LAB_RUN_LIVE=1` and rerun. |
| Exit 2 | Treat as NO_GO; inspect `sessions/_reports/live-worktree-YYYY-MM-DD.json`. |
| Exit 3 | Check `CURSOR_API_KEY`, bridge setup, or `AGENT_LAB_SKIP_LIVE`. |
| Weekly artifact missing | `REPORT=0` skips Tier A artifact writes by design. |
| Live merge artifact missing | Check `sessions/_reports/live-merge-YYYY-MM-DD.json`; Tier C writes only when the live script starts. |

## Related docs

- [Live Cursor worktree dry-run](LIVE-CURSOR-WORKTREE-DRY-RUN.md)
- [Live worktree merge operator](LIVE-MERGE-OPERATOR.md)
- [Stability notes](STABILITY.md)
- [Execute worktree reform](EXECUTE-WORKTREE-REFORM.md)
