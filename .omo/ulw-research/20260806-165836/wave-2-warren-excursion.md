# Excursion E1 — Warren successor

- Trigger: root GitHub metadata contradicted Overstory's shortlist status (`archived=true`) and upstream named Warren as successor.
- `jayminwest/warren@8eb58af…` is active MIT software with a stable release claim and acceptance coverage.
- Strong patterns: provenance-checked event envelope; transactional per-run inbox sequence + atomic unread claim; explicit plan-run/PR gate FSM with bounded retries; salvage-before-destroy and stale-workspace diagnostics.
- Warren drops Overstory's local merge resolver/lock; PR becomes landing boundary. Best-effort teardown, legacy absent-origin trust, salvage size/path limitations and K8s feature differences remain risks.
- Verdict: Warren replaces Overstory in the active shortlist for hosted lifecycle/recovery. Overstory remains historical local-merge reference only.
- Sources: [event envelope](https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/core/event-envelope.ts#L1-L35), [atomic inbox claim](https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/db/repos/run-inbox.ts#L71-L132), [plan coordinator](https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/plan-runs/coordinator.ts#L130-L220), [merge gate](https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/plan-runs/merge-gate.ts#L54-L191), [salvage](https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/runtime/salvage.ts#L1-L99), [destroy gate](https://github.com/jayminwest/warren/blob/8eb58af4317c0fc91194edceddbb8f3c25570cf0/src/runs/reap/destroy.ts#L23-L100).

## EXPAND
- LEAD: absent-origin backward compatibility trust — WHY: possible authority forgery — ANGLE: security refinement.
- DEAD END: Warren as local atomic merge implementation; that layer was dropped.

