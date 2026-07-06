# Gajae Code (GJC) entry — Room vs external pipeline

> **Purpose:** When to stay in Agent Lab Room vs invoke full `gjc` skills, and how to wire external runner slash commands.  
> **Integration map:** [archive/rfcs/GJC-WORKFLOW-PIPELINE.md](./archive/rfcs/GJC-WORKFLOW-PIPELINE.md) · **Handoff schema:** MB-8 in [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md)

---

## When to use which path

| Need | Use | Why |
|------|-----|-----|
| Daily dev mission with Human gates | **Agent Lab Room** (`fast` / `supervisor` preset) | Discuss → plan.md → approve → worktree → Oracle — all in-session |
| Lightweight clarify + plan FSM | **Room + plan_workflow** | In-app clarifier + peer review (ralplan-*like*, not identical artifacts) |
| Full GJC skill FSM (deep-interview → ralplan → ultragoal) | **External `gjc` via slash** | Preserved `.gjc/` artifacts, skill-native phases, tmux team |
| Verify only | **Room execute + Oracle** or **`POST /v1/verify`** | In-session: `AGENT_LAB_ORACLE_LIVE=1` or mock Oracle on merge. External: [VERIFY-API.md](./VERIFY-API.md) + GJC handoff |

**Rule:** Do not expect Room `plan.md` to equal GJC `ralplan` stage files — similar gates, different layout ([GJC-WORKFLOW-PIPELINE](./archive/rfcs/GJC-WORKFLOW-PIPELINE.md) §Implementation notes).

---

## Work UI pipeline stepper (AL-009)

**Tools → Work** shows two rows:

1. **Pipeline** — Interview → Plan → Approve → Goal → Verify (GJC-aligned phases)
2. **Execute detail** — Plan / Review / Execute / Verify / Done (existing WorkStatusBar)

Phase derives from `plan_workflow`, `mission_loop`, and latest execution Oracle — no separate API.

When `AGENT_LAB_EXTERNAL_TOOLS=1`, a **GJC external** badge appears on the pipeline row. Latest execution **GJC handoff** strip shows `external_handoff` summary (MB-8).

---

## Enable external GJC commands

### 1. Environment

```bash
export AGENT_LAB_EXTERNAL_TOOLS=1
```

Restart API (`make dev`). Confirm: `GET /api/health/flags` or Settings → Plugins → External.

### 2. Register commands — `~/.agent-lab/tools.yaml`

```yaml
tools:
  - id: external:gjc-ralplan
    slash: /gjc-ralplan
    label: GJC ralplan
    description: Run gajae-code ralplan in session workspace
    human_approve: true
    cwd: session
    command: gjc ralplan {args}

  - id: external:gjc-ultragoal
    slash: /gjc-ultragoal
    label: GJC ultragoal
    human_approve: true
    cwd: session
    command: gjc ultragoal {args}

  - id: external:gjc-team
    slash: /gjc-team
    label: GJC team
    human_approve: true
    cwd: session
    command: gjc team {args}
```

Placeholders: `{session_id}`, `{args}` (from slash tail).

Repo defaults list stub entries (`external:gjc-*`) until `command` is configured — composer catalog shows them disabled/stub.

### 3. Session allowlist

Settings → Plugins → External → enable tools for the session, or:

```http
PATCH /api/sessions/{id}/external-tools
{ "enabled": ["external:gjc-ralplan", "external:gjc-ultragoal"] }
```

### 4. Run from composer

```
/gjc-ralplan my feature topic
```

Requires `confirm: true` when `human_approve` is set. stdout or `external_handoff.json` in the session folder attaches to `executions[].external_handoff`.

---

## Handoff JSON (required keys)

```json
{
  "stopped_cleanly": true,
  "changed_files": ["src/foo.py"],
  "checks": [{"cmd": "make test", "exit": 0}],
  "evidence_summary": "ralplan final approved; tests green",
  "risks": []
}
```

Attach manually: `POST /api/sessions/{id}/executions/{exec_id}/external-handoff`

**External verify (N9):** post diff + handoff to `POST /v1/verify` — see [VERIFY-API.md](./VERIFY-API.md) · `make n9-verify-consumer` · fixture `sessions/_examples/n9-gjc-handoff.json`

---

## Related env flags

| Flag | Role |
|------|------|
| `AGENT_LAB_EXTERNAL_TOOLS` | Master switch for slash external runner |
| `AGENT_LAB_EXTERNAL_TOOL_TIMEOUT` | Subprocess timeout seconds (default 120) |
| `AGENT_LAB_PLAN_WORKFLOW` | Room plan FSM (default on; `0` disables) |
| `AGENT_LAB_MISSION_LOOP` | Goal/execute mission FSM after plan approve |

---

## References

| Resource | Location |
|----------|----------|
| GJC skill map | [archive/rfcs/GJC-WORKFLOW-PIPELINE.md](./archive/rfcs/GJC-WORKFLOW-PIPELINE.md) |
| External runner code | `src/agent_lab/runtime/external_runner.py` |
| Handoff validation | `src/agent_lab/external_handoff.py` |
| User guide § external | [USER-GUIDE.md](./USER-GUIDE.md) (External tools) |
