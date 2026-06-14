# Plan-First Workflow (Merge Verified)

Plan mode send activates a 5-step FSM that replaces manual Goal Loop entry with agent-proposed `plan.md` and a single Human approval gate.

## Enable

Plan workflow starts automatically on **plan mode send** (`synthesize=true` / Work tab plan toggle).

Disable globally:

```bash
AGENT_LAB_PLAN_WORKFLOW=0
```

Plan-phase agent questions use inbox MCP (same server as execute lane):

```bash
AGENT_LAB_PLAN_INBOX=1   # default: follows AGENT_LAB_EXECUTE_INBOX
```

## Flow

1. **CLARIFY** — Room agents ask via `ask_human` (inbox MCP); scribe blocked while questions pending.
2. **DRAFT** — Scribe writes `plan.md` (includes resolved inbox Q&A).
3. **PEER_REVIEW** — Non-scribe agents CHALLENGE/ENDORSE plan sections (read-only).
4. **REFINE** — Scribe patches plan if needed; Momus-lite mechanical pre-check.
5. **HUMAN_PENDING** — Human approves whole plan in **Plan 승인** panel (Tasks inspector).
6. **APPROVED** — `verified_loop.loop_goal`, `session_goal`, `goal_loop`, and `mission_loop` derived/enabled; execute/dry-run allowed.

## Round limits & Momus-lite

- **Clarify cap** (`max_clarify_rounds`, default 3): after the cap, FSM advances to **DRAFT** anyway; `plan_workflow.notice=clarify_cap_reached` surfaces in banner / Tasks.
- **Peer cap** (`max_peer_review_rounds`, default 2): open objections or Momus-lite rejects no longer loop — phase moves to **HUMAN_PENDING** with `notice=peer_review_cap_reached` or `plan_gate_cap_reached`.
- **Momus-lite gate** during peer: `reject` sends **REFINE** while rounds remain; `last_plan_gate` is shown in REFINE banner and Plan 승인 panel.

## UI receipts & SSE

Turn `complete` events include phase-specific `send_receipt` (`plan_clarify`, `plan_draft`, `plan_peer_review`, `plan_refine`, `plan_pending_approval`, `plan_approved`) plus `plan_workflow_phase` / optional `plan_workflow_notice`.

Mid-turn transitions emit `plan_workflow_phase`; human gate emits `plan_workflow_pending`.

Composer shows phase banners (CLARIFY→REFINE), compact **HUMAN_PENDING** / **APPROVED** hints, and plan-workflow send receipts on the chat tab.

Response contract presets (Settings → Hooks & Response) shape agent envelopes during CLARIFY/PEER; they complement — do not replace — the plan FSM.

## API

| Method | Path |
|--------|------|
| `GET` | `/api/sessions/{id}/plan/workflow` |
| `POST` | `/api/sessions/{id}/plan/approve` |
| `POST` | `/api/sessions/{id}/plan/reject` |

Legacy `POST /verified-loop/approve|reject` delegate to `plan/*` when `plan_workflow.phase=HUMAN_PENDING` (HTTP `Deprecation: true` + `Link` successor header).

`PATCH /goal` returns **409** while `plan_workflow.enabled`.

## Legacy

- Manual **GoalLoopBanner** / **VerifiedLoopBanner** hidden when plan workflow active.
- Composer **verified** turn profile removed; stored `verified` migrates to `analyze`.
- Server structured clarifier (`AGENT_LAB_CLARIFIER`) skipped when plan workflow ON.
- `turn_profile=verified` on plan send redirects to `analyze` + plan workflow (legacy discuss-only still uses verified loop).
- Discuss-only Goal Loop: `AGENT_LAB_GOAL_LOOP=1` with `AGENT_LAB_PLAN_WORKFLOW=0`.

## Related

- [GOAL-LOOP.md](./GOAL-LOOP.md) — Layer 5 legacy discuss goal Oracle
- [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) — execute FSM after plan approve
- [HUMAN-INBOX.md](./HUMAN-INBOX.md) — `ask_human` surface
