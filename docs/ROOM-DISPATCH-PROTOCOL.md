# Room Dispatch Protocol (RDP)

> **Status:** Shipped (CMD-RDP)  
> **Related:** [HOOK-COMMUNICATE-REFORM.md](./HOOK-COMMUNICATE-REFORM.md) · [ROOM-REINFORCEMENT.md](./ROOM-REINFORCEMENT.md) §G3 · [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md)  
> **Fable reference:** sessions `807dbb0a` (Agent Explore×N + Plan), `143dad52` (emergence P3–P5)

---

## 1. Purpose

RDP maps Fable-style **coordinator → scoped workers** onto agent-lab's fixed 3-agent Room without a second scheduler or new envelope `act` vocabulary.

- **Room worker dispatch** (`room_dispatch.py`) — discuss-lane scoped fan-out + ledger  
- **Runtime dispatch** (`runtime.dispatch()`) — Mission/Execute FSM events (RT-H2/H3) — **not merged**

---

## 2. Precedence (one path per human turn)

| Priority | Trigger | Effect |
|----------|---------|--------|
| 1 | `DELEGATE agent: "…"` | Single-agent scoped call; replaces full round |
| 2 | `DISPATCH parallel: a,b: "…"` | N parallel scoped calls + one ledger row |
| 3 | `GO/리드 lead: agent` | Turn lead + R1 split (standard 3N only) |
| 4 | `topic_router` escalation | Consensus budget only (EM-P2 / LC-router) |
| 5 | specialist profile | Asymmetric R1/R2 |
| 6 | default | `run_agent_rounds` / consensus |

Clarifier open → all dispatch skipped.

Dispatch turns **do not enter** `run_consensus_agent_rounds` — P2–P4 emergence mechanics apply only on the default path.

---

## 3. Human syntax

```text
DELEGATE codex: "run parser smoke only"

DISPATCH parallel: codex,cursor: "survey hooks.toml and room_hooks.py"
```

Fan-out cap: `AGENT_LAB_DISPATCH_MAX_FANOUT` (default `3`). Independent of `topic_router` worker routing (LC-router budgets **consensus depth**, not workers).

---

## 4. `run_meta.dispatch_ledger[]`

```json
{
  "id": "disp-001",
  "op": "parallel_delegate",
  "issuer": "human",
  "agents": ["codex", "cursor"],
  "prompt": "...",
  "status": "done",
  "artifact_ids": ["art-1", "art-2"],
  "hook_run_ids": [],
  "topic_category": "standard",
  "started_at": "...",
  "ended_at": "..."
}
```

`op`: `single_delegate` | `parallel_delegate` | `synthesize` | `blocked` (fan-out cap).

Persist via `patch_run_meta` on turn end (same pattern as `last_delegate`, objections).

---

## 5. Hook events (Layer A)

| Event | When | Policy |
|-------|------|--------|
| `pre_dispatch` | Before worker fan-out / single delegate | fail-closed (`stop_on_block=True`) |
| `post_dispatch` | After artifacts + peer summaries | telemetry (`stop_on_block=False`) |

Per-agent `pre_agent_reply` / `post_agent_reply` still run for **each** worker LLM call.

Hook ctx fields: `dispatch_id`, `dispatch_op`, `dispatch_agents`, `topic_route`.

---

## 6. Envelope extension (no new `act`)

Turn lead may emit:

```json
{"act": "MESSAGE", "to": "codex", "dispatch": {"op": "scoped", "prompt": "..."}}
```

Harvest → `dispatch_intents[]` (pending). Execution requires Human send or explicit dispatch marker; see `room_dispatch_intents.py`.

---

## 7. P1–P5 coexistence

| Emergence | RDP interaction |
|-----------|-----------------|
| EM-P1 KPIs | Ledger metrics separate from `communicate_meta.acts` |
| LC-router | Consensus-only; unchanged on dispatch turns |
| EM-P3 objections | Harvest on consensus turn end only |
| EM-P4 recombination | In-loop synthesis; not duplicate of `synthesize` op |
| EM-P5 wisdom | `dispatch_block` is separate context layer |

---

## 8. Verification

| ID | Test |
|----|------|
| CMD-fanout | `tests/test_room_dispatch.py` |
| CMD-hooks | `pre_dispatch` block aborts fan-out |
| CMD-compat | `tests/test_room_delegate_replay.py` |
| CMD-persist | Ledger survives `_write_session_files` |
