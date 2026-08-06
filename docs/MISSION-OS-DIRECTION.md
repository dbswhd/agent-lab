# Mission OS Direction — SSOT

> **Status (2026-06-14):** OS layer roadmap. Workbench UI shell **shipped** (`4d9c5fd`); Web changes are Settings wiring + badges only.  
> **Related:** [PLAN-WORKFLOW.md](archive/rfcs/PLAN-WORKFLOW.md) · [HUMAN-INBOX.md](./HUMAN-INBOX.md) · [CONSOLE-PRODUCTIZATION.md](./CONSOLE-PRODUCTIZATION.md) · [NOTIFICATION-TAXONOMY.md](./NOTIFICATION-TAXONOMY.md)

Agent Lab stays a **Mission OS** (Room consensus · worktree isolation · Oracle verified). Hermes-style **Agent OS** patterns (Gateway, scheduler, skills memory) are absorbed **selectively** without breaking 4C (Merge Verified).

---

## 1. Position

| Choice | Decision |
|--------|----------|
| Product identity | **Mission OS** capability inside the Human-in-the-loop agent development console |
| Extension | dev mission conductor → 24/7 assistant (same brain, different **gate_profile** policy) |
| Deploy | local daemon (launchd/systemd) now → hybrid cloud notify later |
| Gateway | A Web/API → **B outbound** (Phase 1) → **D Telegram** (Phase 2) → **E plugin** (Phase 5); **C skip** |

**Invariants (never bypass):** consensus=Room · isolation=worktree · complete=Oracle verified · BLOCK→execute 409 · Human gate on merge (dev profile).

---

## 2. Naming — `gate_profile` not `lane`

Mission Board already uses `lane` = orchestration lane (`discuss` | `execute` | `verify` | `human`) in `mission_board.py`.

Human/automation policy uses **`gate_profile`**:

```json
{
  "gate_profile": "dev" | "assistant",
  "gate_policy": "strict" | "relaxed"
}
```

Gateway `routes.toml` and schedule entries use `gate_profile` — not Mission Board `lane`.

---

## 3. 4C reference (Merge Verified)

See [PLAN-WORKFLOW.md](archive/rfcs/PLAN-WORKFLOW.md). Shipped FSM in `plan_workflow.py` — **do not break**.

| 4C step | Human gate | Code anchor |
|---------|------------|-------------|
| 1 Discuss | Inbox orchestration (light) | `gate_snapshot.inbox_pending` |
| 2 Plan phase | `ask_human` blocking | `human_inbox.py`, execute MCP |
| 3 Build GO | `propose_build` | `execute_inbox_build_go` |
| 4 Implement | Human diff → merge approve | `plan_execute.resolve_execution`, `merge_checks` |

Merge is **always Human** on `gate_profile=dev`. Assistant may use **trust budget + classifier** as governed bypass (Phase 3).

---

## 4. Human Gates (confirmed)

### Gate 1 — Merge: **D + B**

- `trust_budget.auto_merge_remaining` on `run.json` (distinct from Mission Board `turn_budget`)
- `merge_classifier.py` — low-risk paths (`docs_only`, `test_only`, `single_file`) when verify green
- dev profile: Human merge default; assistant: classifier+budget

### Gate 2 — Plan: **A + B**

- **A (dev):** full Plan-First FSM → `HUMAN_PENDING` → `POST plan/approve`
- **B (assistant recurring):** `sessions/_templates/{id}/` → hash match → `approve_plan_bypass(approved_by="template:{id}")` — skips peer/human pending
- Hash drift → full FSM fallback

### Gate 3 — Inbox: **D + B + A**

- **B:** assistant discuss soft (`INBOX_MODE=soft` equivalent per profile); dev sync pause
- **A:** execute/plan CLARIFY block unchanged
- **D:** Gateway resolve → `POST …/human-inbox/{id}/resolve` (Telegram Phase 2)
- Implementation: `gate_scope.py` 3-tier (`discuss`, `plan_clarify`, `execute`)

### Gate 4 — Skills: **A → B**

- verify PASS → skill draft → Human promote → `.agent-lab/skills/`
- session-local auto on assistant read-only (Phase B)

### Gate 5 — Cron: **A + C + B**

- `run.json` `schedules[]` with pre-approve sign-off
- sandbox unattended for assistant (`PolicyEngine` denies code mutation)
- notify each run (P1 + gateway outbound)

---

## 5. Gateway roadmap

| Phase | Deliverable |
|-------|-------------|
| **1** | `gateway/outbound.py` — webhook fan-out from `~/.agent-lab/gateway.toml` |
| **2** | `gateway/telegram_adapter.py`, `gateway/router.py`, `routes.toml` |
| **5** | `GatewayAdapter` plugins (Discord, CLI, Slack), hybrid relay |

Web Console remains SSOT for dev audit; **24/7 Human loop primary UX = Telegram** (Phase 2+).

---

## 6. Implementation phases

### Phase 0 — Docs ✅

### Phase 1 — Daemon + scheduler + templates + outbound ✅

- `agent-lab serve --daemon` + `AGENT_LAB_MISSION_SCHEDULER=1`
- `mission_scheduler.py` + `run.json` `schedules[]`
- `sessions/_templates/` + `mission_templates.py` + `approve_plan_bypass`
- `gateway/outbound.py` + `GET/PATCH /api/settings/gateway`
- `GET/PATCH /api/sessions/{id}/schedules`, `GET /api/templates`, `GET /api/health/daemon`
- Tests: `tests/test_mission_os_phase1.py`

### Phase 2 — Telegram + `gate_scope.py` ✅

- `gate_scope.py` — `gate_profile`-aware discuss / plan_clarify / execute tiers
- `gateway/router.py` + `~/.agent-lab/routes.toml` (example: `docs/examples/routes.toml`)
- `gateway/telegram_adapter.py` — webhook, `/resolve`, `/approve plan|merge`, inbox push
- API: `POST /api/gateway/telegram/webhook`, `GET /api/gateway/routes`, `POST /api/hooks/{hook_id}`
- Runtime: `GET /api/sessions/{id}/runtime` → `gates.gate_profile`, `gates.discuss`, …
- Tests: `tests/test_mission_os_phase2.py`

### Phase 3 — `trust_budget` + `merge_classifier` ✅

- `run.json` `trust_budget`: `{ auto_merge_remaining, auto_merge_total, classifier_allow[] }`
- `merge_classifier.py`: `docs_only`, `test_only`, `single_file`; deny high-risk paths
- Auto-merge when: `gate_profile=assistant` + merge checks green + classifier + budget > 0
- API: `GET/PATCH …/trust-budget`, `GET …/auto-merge/eligibility`, `POST …/auto-merge`
- Telegram: `/approve auto`
- Tests: `tests/test_mission_os_phase3.py`

### Phase 4 — Skill drafts ✅

- Hook: Oracle verify PASS → skill draft + inbox promote
- Session-local skills in `context_bundle`
- Tests: `tests/test_mission_os_phase4.py`

### Phase 5 — Gateway E + hybrid deploy ✅

- `GatewayAdapter` protocol + registry (`gateway/adapters.py`)
- Adapters: `telegram`, `webhook_inbound`, `cli`, `discord`
- Unified ingress: `process_gateway_ingress(channel, payload)`
- Unified egress: `fan_out_gateway_notify(event, payload)` — outbound + adapters + hybrid
- Hybrid relay: `gateway/hybrid_relay.py` — POST to cloud when `daemon_offline`
- Config: `gateway.toml` → `[adapters]`, `[hybrid]`, `[discord]`
- API: `GET /api/gateway/adapters`, `POST /api/gateway/cli`, `POST /api/gateway/discord/webhook`
- Example: `docs/examples/gateway.toml`
- Hybrid Worker (cloud notify): `docs/HYBRID-RELAY-WORKER.md`, `docs/examples/hybrid-relay-worker.js`
- Tests: `tests/test_mission_os_phase5.py`

---

## 7. UI touch (minimal — no IA redesign)

Workbench shipped: transcript center + `WorkbenchPanel` (`overview|tasks|inbox|plan|background|diff|files|preview|terminal`).

| OS Phase | UI wiring (when backend lands) |
|----------|--------------------------------|
| 1 | Settings: Schedules, Gateway; `NewSessionDialog` template picker — **Settings shipped** |
| 2 | Settings Telegram; Overview gate chips — **GateProfileChips shipped** |
| 3 | Overview / Plan tool badges (trust budget, gate_profile) — **TrustAutoMergeBar shipped** |
| 4 | Inbox `skill_draft` row — **skills segment shipped** |
| 5 | Settings adapter registry — **GatewaySettingsPanel adapters list** |

Optional follow-up (non-blocking): `RunLogPanel` mount, `dry_run`→diff notification routing.

---

## 8. Templates vs eval topics

| Path | Role |
|------|------|
| `sessions/_templates/` | Recurring missions — plan hash + pre-approved fast-path |
| `sessions/_benchmark/topics/dogfood-v1.json` | Eval catalog — quality KPI, not production scheduler |

---

## 9. Code map (Phase 1 shipped / planned)

| Module | Purpose |
|--------|---------|
| `src/agent_lab/gateway/config.py` | Load/save `gateway.toml` |
| `src/agent_lab/gateway/outbound.py` | Webhook delivery |
| `src/agent_lab/mission_scheduler.py` | Cron tick over `schedules[]` |
| `src/agent_lab/mission_templates.py` | Template registry + fast-path approve |
| `src/agent_lab/daemon_state.py` | Daemon pid / last tick |
| `src/agent_lab/plan_workflow.py` | `approve_plan_bypass` for templates |
| `src/agent_lab/gate_scope.py` | gate_profile policy tiers |
| `src/agent_lab/gateway/router.py` | routes.toml mission picker |
| `src/agent_lab/gateway/telegram_adapter.py` | Telegram two-way MVP |
| `src/agent_lab/trust_budget.py` | Auto-merge budget on `run.json` |
| `src/agent_lab/merge_classifier.py` | Low-risk path classifier |
| `src/agent_lab/auto_merge.py` | Eligibility + governed auto-merge |
| `src/agent_lab/skill_drafts.py` | Verify PASS → draft + session skill + promote |
| `app/server/routers/mission_os.py` | Templates, schedules, gateway settings, daemon health |
| `app/server/routers/skill_drafts.py` | Skill draft list / promote / reject API |
| `src/agent_lab/gateway/adapters.py` | GatewayAdapter registry + fan-out |
| `src/agent_lab/gateway/hybrid_relay.py` | Cloud notify when daemon offline |
| `app/server/routers/gateway.py` | Ingress adapters + hooks |
| `app/server/routers/gateway.py` | Telegram webhook + inbound hooks |
