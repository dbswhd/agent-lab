# Wave 2 — Cline

- Typed bridge includes agent/team/pending-prompt snapshots; structured events replace legacy chunk fallback, done dedupe prefers richer result and resets per iteration.
- Tool request contains session/agent/conversation/iteration/toolCallId/tool/input/policy. Missing TUI denies, but controller lacks request ID, timeout, cancellation and idempotency; global/per-request auto-approve can bypass.
- ACP history replay preserves toolCall IDs and status while filtering synthetic prompts; forwarding drops done/error/usage and is fire-and-forget.
- Borrow event union, pending prompt IDs, replay translator, legacy fallback and dedupe. Add durable sequence, decision idempotency/expiry, ack/error path.
- Sources: [event bridge](https://github.com/cline/cline/blob/81cce3d70e10244cdde40dbd0eb0bb711c93006d/apps/cli/src/runtime/session-events.ts), [event tests](https://github.com/cline/cline/blob/81cce3d70e10244cdde40dbd0eb0bb711c93006d/apps/cli/src/runtime/session-events.test.ts), [approvals](https://github.com/cline/cline/blob/81cce3d70e10244cdde40dbd0eb0bb711c93006d/apps/cli/src/runtime/interactive/approvals.ts), [history replay tests](https://github.com/cline/cline/blob/81cce3d70e10244cdde40dbd0eb0bb711c93006d/apps/cli/src/acp/session-load.test.ts).

## EXPAND
- DEAD END: use Cline approval controller directly; lacks durable correlation/idempotency.

