# Wave 1 — worktree/merge

- `jayminwest/overstory@ff38f3f…`: strongest implementation reference: validated worktree creation with rollback, SQLite WAL merge queue, tiered conflict resolution, canonical-content loss guard.
- `smtg-ai/claude-squad@2dd388e…`: base SHA, stale orphan cleanup/prune, existing-branch semantics; substring matching and best-effort branch deletion are risks.
- `nwiizo/ccswarm@3baca0c…`: strongest governance statement: integrate means inspect/merge/archive/reject; no hidden auto-merge.
- Sources: [Overstory manager](https://github.com/jayminwest/overstory/blob/ff38f3f76f084abcc34f519bcaa69580f6e53cf1/src/worktree/manager.ts#L39-L119), [merge resolver](https://github.com/jayminwest/overstory/blob/ff38f3f76f084abcc34f519bcaa69580f6e53cf1/src/merge/resolver.ts#L231-L307), [queue](https://github.com/jayminwest/overstory/blob/ff38f3f76f084abcc34f519bcaa69580f6e53cf1/src/merge/queue.ts#L45-L117), [Claude Squad lifecycle](https://github.com/smtg-ai/claude-squad/blob/2dd388e9857233e07712c8c5b3e2bf3b471b39fa/session/git/worktree_ops.go#L12-L112), [ccswarm governance](https://github.com/nwiizo/ccswarm/blob/3baca0c4ffd8e59fe861a785933db53a4ccfe0d9/docs/CCSWARM_PRODUCT_ABSTRACTION_PLAN.md#L450-L504).

## EXPAND
- LEAD: crash-safe merge reconciliation — WHY: queue state may diverge from Git refs — ANGLE: Overstory tests and failure paths.

