# Wave 2 — Overstory

- Worktree creation and duplicate-branch rejection have focused tests; atomic lock creation/stale recovery is useful.
- Cleanup preserves unmerged branches but swallows deletion failure; queue `dequeue()` deletes rows instead of claim-with-lease, and no stale `merging` or Git-state reconciliation exists.
- GitHub API/root counter-check found `archived=true`; README says no longer maintained and points to Warren.
- Keep as historical pattern source only. Do not recommend dependency/adoption.
- Sources: [manager tests](https://github.com/jayminwest/overstory/blob/ff38f3f76f084abcc34f519bcaa69580f6e53cf1/src/worktree/manager.test.ts#L103-L186), [cleanup tests](https://github.com/jayminwest/overstory/blob/ff38f3f76f084abcc34f519bcaa69580f6e53cf1/src/worktree/manager.test.ts#L441-L501), [lock](https://github.com/jayminwest/overstory/blob/ff38f3f76f084abcc34f519bcaa69580f6e53cf1/src/merge/lock.ts#L47-L105), [queue delete](https://github.com/jayminwest/overstory/blob/ff38f3f76f084abcc34f519bcaa69580f6e53cf1/src/merge/queue.ts#L135-L141), [archive notice](https://github.com/jayminwest/overstory#overstory).

## EXPAND
- LEAD: Warren successor — WHY: changes final ranking — ANGLE: run inbox/gates/recovery/workspaces.

