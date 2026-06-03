# Live Worktree Merge Operator Runbook

Tier C verifies one full live execute path in a disposable git repository:

```text
dry-run worktree -> Human approve -> merge into disposable base branch
```

It never targets the `agent-lab` repo root, production sessions, or GitHub Actions.

## When

Run Tier C:

- right after Tier B returns GO
- after execute/worktree/merge code changes
- once per branch cut as an operator confidence check

## Preconditions

| Requirement | Check |
|-------------|-------|
| Tier A green | `make verify-ops REPORT=0` |
| Live guard | `AGENT_LAB_RUN_LIVE=1` |
| Cursor ready | `CURSOR_API_KEY` present and bridge health ready |
| Target repo | Disposable temp repo only |

The implementation creates a temporary parent such as `/tmp/agent-lab-live-merge-*` unless `--work-dir` is explicitly provided. Reports are written under gitignored `sessions/_reports/`.

## Operator Command

```bash
cd /path/to/agent-lab
AGENT_LAB_RUN_LIVE=1 make verify-ops-live-merge
```

To skip the Tier A preflight after it has already passed:

```bash
AGENT_LAB_RUN_LIVE=1 SKIP_PREFLIGHT=1 make verify-ops-live-merge
```

Expected final line:

```text
Live merge ops report: sessions/_reports/live-merge-YYYY-MM-DD.json (GO)
```

## Operator Prompt

The live script uses the same minimal plan action pattern as Tier B:

```markdown
## 지금 실행
1.
   - 무엇을: Add one line `LIVE_M0_OK` to src/spike.txt (minimal live M0 check).
   - 어디서: `src/spike.txt`
   - 검증: `src/spike.txt` contains `LIVE_M0_OK`
```

Human gate:

1. Cursor dry-run edits the isolated worktree.
2. The execution reaches `pending_approval`.
3. The operator checks the report diff and approves.
4. `resolve_execution(..., vote="approve")` merges the exec branch into the disposable base branch.
5. The report verifies `merge.commit_sha`, clean base branch, removed worktree, removed exec branch, and `LIVE_M0_OK` in `src/spike.txt`.

## Go / No-Go

| Check | GO means |
|-------|----------|
| `main_clean_before` | Disposable base repo started clean. |
| `pending_approval` | Dry-run stopped at the Human gate. |
| `approve_status_merged` | Approve path returned `status: merged`. |
| `merge_commit_sha_present` | Merge metadata recorded the merged commit. |
| `base_branch_contains_marker` | Disposable base branch contains `LIVE_M0_OK`. |
| `main_clean_after_merge` | Disposable base repo is clean after merge. |
| `worktree_removed_after_merge` | Execution worktree was discarded after merge. |
| `exec_branch_removed_after_merge` | Execution branch was deleted. |

Exit codes are shared with Tier B:

| Code | Meaning |
|------|---------|
| 0 | GO |
| 1 | Usage or missing `AGENT_LAB_RUN_LIVE=1` guard |
| 2 | NO_GO |
| 3 | SKIPPED, usually missing key/bridge or `AGENT_LAB_SKIP_LIVE=1` |

## Rollback

| Situation | Action |
|-----------|--------|
| Before merge, reject is needed | Use the existing reject path: `resolve_execution(..., vote="reject")`. |
| After merge, result is wrong | In the disposable repo only: `git reset --hard <pre_merge_sha>`, shown in the JSON report under `rollback.reset_command`. |
| Worktree orphan remains | Run `python scripts/check_worktree_orphans.py`; inspect the disposable session folder if `--keep-artifacts` was used. |
| Report status is `no_go` | Inspect `sessions/_reports/live-merge-YYYY-MM-DD.json` and rerun after fixing the bridge or merge path. |

## Never

- Do not target the `agent-lab` repo root.
- Do not use production sessions.
- Do not force-push.
- Do not add this target to GitHub Actions.
- Do not use Tier C as a merge conflict UI test.

## Related

- [Agent Lab Ops Runbook](OPS-RUNBOOK.md)
- [Live Cursor worktree dry-run](LIVE-CURSOR-WORKTREE-DRY-RUN.md)
- [Execute worktree reform](EXECUTE-WORKTREE-REFORM.md)
