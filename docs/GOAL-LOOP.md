# Goal-Driven Session Loop

> **Legacy (discuss-only):** Default plan sessions use [PLAN-WORKFLOW.md](./PLAN-WORKFLOW.md) (Merge Verified). Manual `PATCH /goal` is disabled while `plan_workflow.enabled`.

Layer 5 lets a Human define a session-level goal and lets an independent, mock-first Oracle decide whether a completed Room turn demonstrated that goal.

## Enable

```bash
AGENT_LAB_GOAL_LOOP=1
```

The default Oracle is deterministic and offline. Put concrete completion literals in backticks, for example: `결론에 \`GOAL_OK\`를 기록한다`. A goal check passes when the transcript contains every literal. Without backticks, the mock Oracle uses a bounded keyword heuristic.

Set `AGENT_LAB_GOAL_ORACLE_LIVE=1` or `AGENT_LAB_ORACLE_LIVE=1` to opt into the Claude `oracle` role. Responses use structured `VERDICT` / `EVIDENCE` (see [LIVE-ORACLE.md](./LIVE-ORACLE.md)). CI and regression fixtures never require it.

## Human Gate

After each discuss or plan turn, an enabled open goal is checked once, up to `goal_loop.max_checks` (default 5).

- PASS: `goal_loop.status` becomes `achieved`.
- FAIL: the reason remains visible and **한 턴 더 토론** pre-fills the Composer. Human still sends the next turn.
- `AGENT_LAB_GOAL_AUTO_CONTINUE=1`: explicitly opts into exactly one extra discuss round after a FAIL. The extra round cannot recurse; a second FAIL returns to the Human gate.

Manual checks use `POST /api/sessions/{id}/goal/check`. Goal setting and edits use `PATCH /api/sessions/{id}/goal`.

Layer 5 is independent from Layer 3 execute verification. It does not read or mutate execution Oracle state.
