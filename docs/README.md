# Agent Lab documentation index

> **Updated:** 2026-06-18 · **Tests:** `pytest -m "not live"` · **Smoke:** regression baselines · **Hook/communicate:** `make verify-hooks`

Use this page to pick the **one canonical doc** for your question. Older numbered guides (`00`–`05`) and early RFCs are kept for history but **must not** be used as shipped-status sources.

**New:** [ARCHITECTURE.md](./ARCHITECTURE.md) — 기능·백엔드·프론트·UX **전체 분류 지도** (모듈/라우터/컴포넌트 맵).

---

## 질문별 빠른 찾기

| 질문 | 문서 |
|------|------|
| 시스템 전체 구조·레이어 | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| 기능·동작·API·UI 상태 | [USER-GUIDE.md](./USER-GUIDE.md) |
| shipped / partial / future | [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) |
| 백엔드 Room / execute / mission | ARCHITECTURE §3–4 · USER-GUIDE §7–9 · [PLAN-WORKFLOW.md](./PLAN-WORKFLOW.md) · [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) |
| 프론트 컴포넌트·IA | ARCHITECTURE §5–6 · [developer-agent-console.md](./developer-agent-console.md) · [UI-IA-ROADMAP.md](./UI-IA-ROADMAP.md) |
| UX gap / productization | [UI-MIGRATION-GAPS.md](./UI-MIGRATION-GAPS.md) · [CONSOLE-PRODUCTIZATION.md](./CONSOLE-PRODUCTIZATION.md) |
| Gateway · scheduler · Mission OS | [MISSION-OS-DIRECTION.md](./MISSION-OS-DIRECTION.md) · [MISSION-OS-OPS.md](./MISSION-OS-OPS.md) |
| Human Inbox · MCP | [HUMAN-INBOX.md](./HUMAN-INBOX.md) · [MCP-TOOL-CONTRACT.md](./MCP-TOOL-CONTRACT.md) |
| Runtime harness · external runner | [RUNTIME-HARNESS-PLAN.md](./RUNTIME-HARNESS-PLAN.md) · [ROOM-DISPATCH-PROTOCOL.md](./ROOM-DISPATCH-PROTOCOL.md) |
| Trading extension | [extensions/QUANT-TRADING.md](./extensions/QUANT-TRADING.md) · [trading-mission/](./trading-mission/) |
| CI · regression · live ops | [STABILITY.md](./STABILITY.md) · [OPS-RUNBOOK.md](./OPS-RUNBOOK.md) · Tier 5 runbooks |
| MD / PROJECT.md 작성 | [MD-WRITING-PLAN.md](./MD-WRITING-PLAN.md) |
| 레거시 early design | Tier 4 only — **not** for shipped status |

---

## Tier 1 — Canonical (plan vs code, daily ops)

| Doc | Use when |
|-----|----------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | **System map** — backend routers, core modules, frontend components, UX flows |
| [USER-GUIDE.md](./USER-GUIDE.md) | Product behavior, env flags, Room · execute · UI |
| [EXTERNAL-REFS-TRACEABILITY.md](./EXTERNAL-REFS-TRACEABILITY.md) | **What is shipped** — evidence paths, partial/future queue |
| [EXTERNAL-REFS-PLAN.md](./EXTERNAL-REFS-PLAN.md) | **Why** external ideas were adopted (history; queue empty) |
| [STABILITY.md](./STABILITY.md) | Regression baselines, smoke, CI expectations |
| [OPS-RUNBOOK.md](./OPS-RUNBOOK.md) | Manual verify tiers, live worktree ops |
| [EVAL-PROGRAM.md](./EVAL-PROGRAM.md) | Live dogfood test program — topic catalog, weekly matrix, KPI loop |
| [CLAUDE.md](../CLAUDE.md) | Repo dev quick start (root, not `docs/`) |

**Rule:** If two docs disagree, **TRACEABILITY + code + tests** win.

---

## Tier 2 — Feature RFCs (shipped core + explicit backlog)

| Doc | Status (2026-06-07) |
|-----|---------------------|
| [HOOK-COMMUNICATE-REFORM.md](./HOOK-COMMUNICATE-REFORM.md) | Phase 0–5 **shipped** incl. `LEGACY_ENDORSE` default off |
| [EXECUTE-WORKTREE-REFORM.md](./EXECUTE-WORKTREE-REFORM.md) | Worktree execute/merge **shipped** |
| [MISSION-OS-DIRECTION.md](./MISSION-OS-DIRECTION.md) | **Mission OS SSOT** — gate_profile, Human Gates 1–5, Gateway roadmap, Phase map |
| [HUMAN-INBOX.md](./HUMAN-INBOX.md) | Execute MCP + API **shipped**; plan-first §3.4.3 synced 2026-06-14 |
| [GOAL-LOOP.md](./GOAL-LOOP.md) | Mock-first goal Oracle **shipped**; live Oracle opt-in |
| [LIVE-ORACLE.md](./LIVE-ORACLE.md) | Execute + goal Oracle prompts, evidence, env flags |
| [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) | **Shipped** — Layer 6 FSM + Track B/C/D ([TRACEABILITY](./EXTERNAL-REFS-TRACEABILITY.md) §ML-*) |
| [MISSION-BOARD-ADOPTION.md](./MISSION-BOARD-ADOPTION.md) | **Shipped** — Mission Board MB-9…MB-11 (Paperclip/OmO/Conductor/Hermes adoption) |
| [RUNTIME-HARNESS-PLAN.md](./RUNTIME-HARNESS-PLAN.md) | **H0–H4 shipped** — runtime contract, dispatch lanes, PolicyEngine |
| [ROOM-REINFORCEMENT.md](./ROOM-REINFORCEMENT.md) | Benchmark / delegate / score **shipped** |
| [PLUGIN-DISCOVERY.md](./PLUGIN-DISCOVERY.md) | Slash commands + plugins **shipped** |
| [NOTIFICATION-TAXONOMY.md](./NOTIFICATION-TAXONOMY.md) | Toast / Activity kinds |
| [PLAN-WORKFLOW.md](./PLAN-WORKFLOW.md) | Plan-First FSM — clarify → approve → execute |
| [ROOM-DISPATCH-PROTOCOL.md](./ROOM-DISPATCH-PROTOCOL.md) | DELEGATE / parallel dispatch protocol |
| [MCP-TOOL-CONTRACT.md](./MCP-TOOL-CONTRACT.md) | MCP tool contract for inbox / session plugins |
| [MISSION-OS-OPS.md](./MISSION-OS-OPS.md) | Mission OS operational notes |
| [MISSION-DOGFOOD.md](./MISSION-DOGFOOD.md) | Mission dogfood procedures |
| [HYBRID-RELAY-WORKER.md](./HYBRID-RELAY-WORKER.md) | Cloudflare hybrid relay worker |
| [AGENT-OS-MODE-SIMPLIFICATION-PLAN.md](./AGENT-OS-MODE-SIMPLIFICATION-PLAN.md) | Agent OS mode simplification (planning) |

### Extensions & trading

| Doc | Role |
|-----|------|
| [extensions/QUANT-TRADING.md](./extensions/QUANT-TRADING.md) | Quant trading extension overview |
| [trading-mission/THIN-RUNTIME.md](./trading-mission/THIN-RUNTIME.md) | Thin runtime for trading missions |
| [trading-mission/OFFLINE-LANE.md](./trading-mission/OFFLINE-LANE.md) | Offline lane |
| [trading-mission/SCHEDULER.md](./trading-mission/SCHEDULER.md) | Trading scheduler |
| [trading-mission/topic_template.md](./trading-mission/topic_template.md) | Live topic template |
| [trading-mission/offline_topic_template.md](./trading-mission/offline_topic_template.md) | Offline topic template |

---

## Tier 3 — UI migration (cosmetic / IA; does not block backend)

| Doc | Notes |
|-----|--------|
| [CONSOLE-PRODUCTIZATION.md](./CONSOLE-PRODUCTIZATION.md) | Productization SSOT: IA P0, Hooks/Response P1, verification P2, bridge lifecycle P3 |
| [UI-MIGRATION-GAPS.md](./UI-MIGRATION-GAPS.md) | Prototype vs app gaps (titlebar Inbox, classic mode, CSS bridge, …) |
| [UI-IA-ROADMAP.md](./UI-IA-ROADMAP.md) | Deprecate list + target IA |
| [UI-HANDOFF-TEAM-AGENTS.md](./UI-HANDOFF-TEAM-AGENTS.md) | Polish checklist for Room UI |
| [developer-agent-console.md](./developer-agent-console.md) | Current console UI reference |
| [WORK-TAB-IA.md](./WORK-TAB-IA.md) | Work tab layout notes |

**Rule:** Failing UI *contract* tests are updated to match **current** components, not reverted to prototype naming.

---

## Tier 4 — Legacy / educational (do not use for status)

| Doc | Superseded by |
|-----|----------------|
| [00-GETTING-STARTED.md](./00-GETTING-STARTED.md) | USER-GUIDE §1–2 |
| [01-CONTROLLED-WORKFLOW-SYSTEM.md](./01-CONTROLLED-WORKFLOW-SYSTEM.md) | USER-GUIDE, TRACEABILITY |
| [02-ui-ux-handoff.md](./02-ui-ux-handoff.md) | developer-agent-console.md |
| [03-workflow.md](./03-workflow.md) | USER-GUIDE §Room |
| [04-multi-agent-room.md](./04-multi-agent-room.md) | USER-GUIDE §9 |
| [05-room-agent-roles.md](./05-room-agent-roles.md) | USER-GUIDE, prompts in code |
| [ui-improvements.md](./ui-improvements.md) | UI-MIGRATION-GAPS |
| [SPRINT-D-CHECKLIST.md](./SPRINT-D-CHECKLIST.md) | STABILITY / closed sprint |
| [MD-SYSTEM-DESIGN.md](./MD-SYSTEM-DESIGN.md) | MD-WRITING-PLAN (authoring); TRACEABILITY (shipped) |

**Archived handoffs / audits:** [archive/](./archive/) — do not use for status.

### Root & `.hermes/` (repo 외부 tier)

| Doc | Role | Note |
|-----|------|------|
| [../README.md](../README.md) | Project overview, quick start | |
| [../CLAUDE.md](../CLAUDE.md) | Dev quick start | Tier 1 canonical |
| [../AGENTS.md](../AGENTS.md) | Coding conventions | |
| [../Agent-Lab Stabilization Plan.md](../Agent-Lab%20Stabilization%20Plan.md) | Stabilization backlog | **Duplicate** of `.hermes/plans/agent-lab-stabilization.md` — prefer `.hermes/` for edits |
| `../.hermes/plans/agent-lab-stabilization.md` | Same stabilization plan | Hermes-format SSOT |
| `../.agent-lab/PROJECT.md` | Workspace project memory | Runtime-injected, not design doc |

---

## Tier 5 — Authoring & live ops runbooks

| Doc | Role |
|-----|------|
| [MD-WRITING-PLAN.md](./MD-WRITING-PLAN.md) | How to write PROJECT.md, CLAUDE.md, skills |
| [LIVE-CURSOR-WORKTREE-DRY-RUN.md](./LIVE-CURSOR-WORKTREE-DRY-RUN.md) | Disposable repo dry-run |
| [LIVE-MERGE-OPERATOR.md](./LIVE-MERGE-OPERATOR.md) | Live merge operator |
| [LIVE-VERIFICATION-ECONOMICS-SAFETY.md](./LIVE-VERIFICATION-ECONOMICS-SAFETY.md) | Live/manual checklist — cost_ledger budget (G1+G2) · diff safety scan (G6) · tracing (G5) · judge (G8) |
| [TUNNEL-LAUNCHD-SOAK-RUNBOOK.md](./TUNNEL-LAUNCHD-SOAK-RUNBOOK.md) | Tier E — launchd + tunnel mission-wake soak |
| [LC-L4-ADVERSARIAL-LIVE.md](./LC-L4-ADVERSARIAL-LIVE.md) | Live adversarial gate opt-in |
| [HUMAN-INBOX-CLAUDE-HANDOFF.md](./HUMAN-INBOX-CLAUDE-HANDOFF.md) | Claude-side handoff notes |
| [APP.md](./APP.md) | App packaging notes |
| [apple-kit-specs.md](./apple-kit-specs.md) | macOS visual specs |

---

## Quick commands

```bash
make dev              # API + web
make test             # full pytest (not live)
make verify-hooks     # Hook · Communicate suite
make ci               # test + smoke + score fixtures
make measure-communicate-baseline
```
