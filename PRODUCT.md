# Agent Lab — Product Context

> Impeccable / design-agent context. Visual tokens: `web/DESIGN.md` · Features: `docs/USER-GUIDE.md`

## Register

**product** — desktop Mission OS for coordinating coding agents; design serves throughput and trust, not marketing spectacle.

## Target users

Developers and technical leads running multi-agent Room sessions, plan/execute/verify loops, and human-inbox decisions — often for hours without leaving the app.

## Product purpose

Quiet operations console: **Discuss → plan.md → worktree execute → Oracle verify**. Human approves direction; agents argue and implement in isolation.

## Brand personality

- Calm, legible, trustworthy under load
- Progressive disclosure: outcomes prominent; diagnostics available on demand
- Neutral graphite palette — not playful SaaS, not terminal brutalism
- Signature: one decision surface at a time; no stacked approval modals

## Anti-references

- Generic AI dashboard (purple gradients, Inter, card-in-card stacks)
- Chat-only UI with no workbench or verify state
- Flashy motion on every keystroke or tab change
- Replacing worktree / Oracle gates with prettier buttons

## Strategic design principles

1. **Tokens first** — `web/src/styles/tokens.css` is SSOT; no ad-hoc hex in TSX.
2. **Tonal depth, not shadow stacks** — hairlines + surface steps; reserve strong shadow for modals.
3. **Status = icon + label + color** — never color alone.
4. **Desktop-first density** — Tauri shell; compact type ramp; composer dock stable.
5. **Presentation-only migration** — UI work must not change API contracts or execute gates.

## Primary surfaces

| Surface | Role |
|---------|------|
| Session rail | Session list, new session, archive |
| Transcript + composer | Room chat, mentions, slash commands |
| Workbench | Overview, tasks, human inbox, tools (diff, files, terminal) |
| Plan / Execute panel | Work stepper, plan cards, execute queue, verify evidence |
