# Agent Lab documentation index

> **Updated:** 2026-06-10 · **Tests:** `791 collected` (`pytest -m "not live"`) · **Smoke:** 32 regression baselines · **Hook/communicate:** `make verify-hooks`

Use this page to pick the **one canonical doc** for your question. Older numbered guides (`00`–`05`) and early RFCs are kept for history but **must not** be used as shipped-status sources.

---

## Tier 1 — Canonical (plan vs code, daily ops)

| Doc | Use when |
|-----|----------|
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
| [HUMAN-INBOX.md](./HUMAN-INBOX.md) | Execute MCP + API **shipped**; full Inbox UI / discuss harvest **partial** |
| [GOAL-LOOP.md](./GOAL-LOOP.md) | Mock-first goal Oracle **shipped**; live Oracle opt-in |
| [LIVE-ORACLE.md](./LIVE-ORACLE.md) | Execute + goal Oracle prompts, evidence, env flags |
| [MISSION-LOOP-C-OMO.md](./MISSION-LOOP-C-OMO.md) | **Shipped** — Layer 6 FSM + Track B/C/D ([TRACEABILITY](./EXTERNAL-REFS-TRACEABILITY.md) §ML-*) |
| [MISSION-BOARD-ADOPTION.md](./MISSION-BOARD-ADOPTION.md) | **Shipped** — Mission Board MB-9…MB-11 (Paperclip/OmO/Conductor/Hermes adoption) |
| [RUNTIME-HARNESS-PLAN.md](./RUNTIME-HARNESS-PLAN.md) | **H0–H4 shipped** — runtime contract, dispatch lanes, PolicyEngine |
| [ROOM-REINFORCEMENT.md](./ROOM-REINFORCEMENT.md) | Benchmark / delegate / score **shipped** |
| [PLUGIN-DISCOVERY.md](./PLUGIN-DISCOVERY.md) | Slash commands + plugins **shipped** |
| [NOTIFICATION-TAXONOMY.md](./NOTIFICATION-TAXONOMY.md) | Toast / Activity kinds |

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

---

## Tier 5 — Authoring & live ops runbooks

| Doc | Role |
|-----|------|
| [MD-WRITING-PLAN.md](./MD-WRITING-PLAN.md) | How to write PROJECT.md, CLAUDE.md, skills |
| [LIVE-CURSOR-WORKTREE-DRY-RUN.md](./LIVE-CURSOR-WORKTREE-DRY-RUN.md) | Disposable repo dry-run |
| [LIVE-MERGE-OPERATOR.md](./LIVE-MERGE-OPERATOR.md) | Live merge operator |
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
