---
name: agent-lab-ui
description: Agent Lab Mission OS UI — custom CSS tokens, 3-pane shell, Work stepper, Room transcript. Use when polishing, migrating, or extending web/src components. Enforces tokens.css, no Tailwind, and UI-MIGRATION-GAPS scope.
tools: Read, Edit, Bash
---

# Agent Lab UI

Project-specific UI skill for **Human-in-the-loop Mission OS** desktop shell (Tauri + React + Vite).

## When to use

- Visual polish, layout fixes, motion, density, IA alignment
- Work UI (Plan → Review → Execute → Verify), RoomChat, Workbench, Inbox, CommandPalette
- Closing gaps in `docs/archive/legacy/UI-MIGRATION-GAPS.md` (cosmetic tier — logic/API unchanged)

Pair with: `/impeccable`, `/emil-design-eng`, `/review-animations`, `/fixing-motion-performance`.

## Stack (non-negotiable)

| Rule | Detail |
|------|--------|
| Styles | `web/src/styles/` only — **Tailwind, styled-components, inline theme libs 금지** |
| Load order | `main.tsx`: tokens → base → layout → surfaces → plan-execute → overlays → tweaks → prototype-panels |
| Tokens SSOT | `web/src/styles/tokens.css` — use `--surface-*`, `--label-*`, `--space-*`, `--radius-*`, `--transition` |
| Design spec | Read `web/DESIGN.md` before changing look & feel |
| Components | `web/src/components/` PascalCase; API via `web/src/api/client.ts` only |
| State | React state + context — Redux/Zustand 금지 |

## IA (3-pane shell)

```text
Session rail | Transcript + Composer | Workbench (overview / tasks / inbox / tools)
```

- Work stepper: Plan → Review → Execute → Verify → Done (`WorkStatusBar`, `PlanExecutePanel`)
- Tools tabs: ⌘1–7 (transcript, work, background, diff, files, preview, terminal)
- Canonical class families: `.shell`, `.rail__*`, `.pane`, `.taskbar__*`, `.work-surface`, `.plan-card__*`, `.chat-turn`

## Priority surfaces (polish order)

1. `WorkStatusBar.tsx` + `PlanExecutePanel.tsx` + `plan-execute.css`
2. `RoomChat.tsx` + `ChatComposer.tsx` + `layout.css` / `surfaces.css`
3. Production-only UI (prototype HTML 없음 — tokens + DESIGN.md로 스타일): `CommandPalette`, `NotificationCenter`, `WorkPanel`, `ExecuteQueueBar`
4. Context sidebar: `ContextOverviewPanel`, `HumanInboxPanel`, `InspectorPane`

## Known gaps (do not “fix” logic)

Read `docs/archive/legacy/UI-MIGRATION-GAPS.md` §2–3. Examples:

- Shell grid vs flex (동작 OK, 구조만 다름)
- SessionList agent avatar strip 미구현
- Activity vs Inbox routing 차이 — see `NOTIFICATION-TAXONOMY.md`

**Conflict rule:** code + contract tests win over migration doc.

## Motion

- Animate **transform, opacity, color** only (`web/DESIGN.md` §6)
- UI transitions ≤ 300ms; honor `prefers-reduced-motion`
- Keyboard/high-frequency actions (⌘K, tab switch): minimal or no motion
- After CSS motion changes: invoke `/review-animations` on touched files

## Anti-patterns (Agent Lab)

- Generic “AI slop”: Inter + purple gradient, nested bordered cards, gray body on tinted bg
- New raw hex in components — use tokens
- Dual legacy classes (`.plan-execute-panel__*` etc.) — M6 removed; use canonical names only
- Breaking execute/objection gates for prettier UI

## Verification (run before done)

```bash
cd web && npm run build
cd web && npm run format:check
cd web && npx react-doctor . --verbose --diff 2>/dev/null || true
pytest tests/test_workspace_ui_contract.py tests/test_liquid_glass_scope_contract.py -q
```

## Reference repos (patterns only — do not merge stacks)

- `bytedance/deer-flow` `frontend/` — workspace chat IA (shadcn stack; copy IA not deps)
- `JohnRiceML/clawport-ui` — agent dashboard density, themes, live logs

## Docs

| Question | Path |
|----------|------|
| Design system | `web/DESIGN.md` |
| UI migration gaps | `docs/archive/legacy/UI-MIGRATION-GAPS.md` |
| UX / features | `docs/USER-GUIDE.md` §4, §18 |
| Skill install | `docs/UI-SKILLS.md` |
