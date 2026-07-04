# Turn modes — current contract (2026-06)

> **SSOT (code):** `src/agent_lab/turn_modes.py` · **UI:** `web/src/utils/roomPresets.ts` · `RoomChat.tsx` · `ChatComposer.tsx`  
> **TurnPolicy (Wave F — Plan toggle deprecation):** [TURN-POLICY.md](./TURN-POLICY.md) — **shipped:** Composer Plan toggle removed; `AGENT_LAB_TURN_POLICY=1` default; API `mode`/`synthesize` deprecated hints only.  
> **Related:** [05-room-agent-roles.md](./05-room-agent-roles.md) · [USER-GUIDE.md §6](./USER-GUIDE.md) · [FLOW.md](./FLOW.md)

Agent Lab exposes **two independent controls** at send time. Do not confuse them with removed legacy UI labels (`discuss`, `analyze`, `review`, `free`, `♾️` segmented picker).

---

## 1. Control axes

| Axis | User-facing | Values | What it controls |
|------|-------------|--------|------------------|
| **Room preset** | Composer — **빠른 / 감독** | `fast` · `supervisor` | Agent count, consensus, default plan policy, Inbox harvest |
| **Plan toggle** | Composer — **Plan** checkbox | OFF · ON | API `mode` (`discuss` \| `plan`), Scribe after turn, read-only overlay |

**Runtime turn profile** (`quick` · `team` · `loop`) is derived from preset + payload. There is **no** quick/team/loop segmented picker in the current UI.

---

## 2. Room preset (Composer)

| Preset | UI | `turn_profile` | Agents | Consensus | Plan toggle default | Toggle editable? |
|--------|-----|----------------|--------|-----------|---------------------|------------------|
| **fast** | 빠른 | `quick` | 1 lead | OFF | OFF | **Locked OFF** |
| **supervisor** | 감독 | `loop` | team (typ. 3+) | ON | ON | **Locked ON** (except plan-workflow Human approval wait) |

Preset is stored on `run.json` (`room_preset`) and sent as form field `preset` on each run.

**Fast Inbox:** orchestrator discuss harvest / plan CLARIFY inbox **skipped**; team-lead MCP (`ask_human` / `propose_build`) and execute lane **kept** — [05-room-agent-roles.md §Fast preset](./05-room-agent-roles.md).

---

## 3. Runtime profiles (`quick` · `team` · `loop`)

Parsed by `resolve_mode_contract()` in `turn_modes.py`. Used for rounds, consensus, and plan intent — not shown as a 3-way Composer picker.

| Profile | R1 | `consensus_mode` | Typical preset | `plan_intent` |
|---------|----|--------------------|----------------|---------------|
| **quick** | 1 lead agent | off | fast | `none` |
| **team** | selected agents parallel | off | (API/legacy only) | optional plan |
| **loop** | selected agents | on | supervisor | `loop` (plan required for new loop inputs) |

### Legacy aliases (API / localStorage only)

Old turn-profile strings are **accepted for backward compatibility** and normalized:

| Legacy input | Maps to |
|--------------|---------|
| `discuss`, `analyze` | **team** |
| `free`, `review`, `verified`, `specialist` | **loop** |
| `quick` | **quick** |

**Removed from UI (2026-06):** segmented picker for discuss / analyze / review / free / ♾️.  
Historical migration: [archive/rfcs/AGENT-OS-MODE-SIMPLIFICATION-PLAN.md](./archive/rfcs/AGENT-OS-MODE-SIMPLIFICATION-PLAN.md).

---

## 4. Plan toggle — OFF vs ON (detailed)

The Plan checkbox sets `planAfterSend` in the client. On send:

- **OFF** → `mode: "discuss"`, `synthesize: false`
- **ON** → `mode: "plan"`, `synthesize: true`

Backend entry: `continue_room_round(..., synthesize=…)` / `run_room(..., synthesize=…)` in `room/turn_flow.py`.

### 4.1 Turn pipeline differences

| Step | Plan OFF (`discuss`) | Plan ON (`plan`) |
|------|----------------------|------------------|
| Clarifier | topic short / first turn | + plan-context question set on first synthesize |
| Agent invoke | `apply_discuss_executor_policy(discuss=True)` | full permissions per agent |
| Codex / Claude | read-only overlay (`claude.write=false`, discuss preamble) | tools/write per permissions |
| Kimi Work | read-only — verify repo, `[PROPOSED:]` only | same — **no execute/patch claims** in either mode |
| Cursor | tools on (execute still separate Human gate) | tools on |
| Scribe (`plan_scribe`) | **skipped** (E2b: open objections → `## 미해결 이의` patch only) | **runs** — updates `sessions/<id>/plan.md` |
| Task harvest | `[PROPOSED:]` → `tasks[]`; **no** pre-claim / plan link sync | + plan refs / scribe linkage |
| Inbox harvest | **off by default** — opt-in `AGENT_LAB_ORCHESTRATOR_INBOX_HARVEST=1` | same — plan-workflow CLARIFY via MCP `ask_human`, not orchestrator scrape |
| Turn receipt (`run.json`) | `discuss_saved` | `plan_updated` |
| SSE `complete` | same receipt field | same |

### 4.2 Agent payload (`[고정 constraints]`)

Policy is injected into constraints — agents must **not** open with meta like 「discuss/plan 모드입니다」.

**Plan OFF — discuss lane behavior:**

- Read/search repo to support claims; no casual file edits via Codex/Claude
- Execution proposals as **`[PROPOSED: …]`** text only
- Loop R2+: prefer `agent-envelope` acts (`ENDORSE`, `CHALLENGE`, …)

**Plan ON — plan lane behavior:**

- Scribe synthesizes agreed/open items into `plan.md` after the agent round
- Execute sections in plan remain behind Human gate until Work approve + execute lane

### 4.3 When the toggle is locked

| Condition | Plan toggle |
|-----------|-------------|
| Preset **fast** | forced **OFF** (`changePlanAfterSend` no-op) |
| Preset **supervisor** | forced **ON** (disabled in UI; exception: `plan_workflow` awaiting Human approval → OFF until resolved) |
| `turn_profile === "loop"` without preset | forced **ON** |
| `plan_workflow` awaiting approval | **OFF** until Human acts |

### 4.4 「지금 정리」 (synthesize-only)

Work / plan toolbar triggers **`synthesize_only`** via `runSynthesizeOnly()` / dedicated SSE workflow `room.synthesize_only` — Scribe pass **without** agents or a new Human message. **SSOT is `synthesize_only=true` + `session_id`**; deprecated `mode` / `synthesize` form fields are ignored on this path.

---

## 5. Naming: product flow vs API mode

| Term | Meaning |
|------|---------|
| **Product flow "Discuss"** | Room debate phase before `plan.md` is approved (see [FLOW.md](./FLOW.md) diagram) |
| **API / compose `discuss`** | Single turn with **Plan toggle OFF** — Scribe does not run |
| **Legacy profile `discuss`** | Old UI label → now **team** runtime profile — **do not use in new docs** |

---

## 6. Send payload (summary)

`POST /api/room/runs` (SSE):

| Field | Role |
|-------|------|
| `preset` | `fast` \| `supervisor` |
| `mode` | `discuss` \| `plan` (from Plan toggle) |
| `turn_profile` | usually preset-derived; legacy strings normalized |
| `consensus_mode` | preset supervisor → true |
| `synthesize_only` | Scribe-only run |
| `agents[]`, `topic`, `permissions`, `workspace`, … | unchanged |

---

## 7. Verification

```bash
make test-fast   # includes mode contract + fast inbox skip
pytest tests/test_turn_modes.py tests/test_fast_inbox_skip.py -q
pytest tests/test_workspace_ui_contract.py -q -k "composer or plan"
```

Regression fixtures: `sessions/_regression/discuss_*`, `sessions/_regression/plan_*`.
