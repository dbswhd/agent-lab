# Production Audit — 2026-06-14

> **Archived 2026-06-14** — point-in-time audit. Shipped status: [EXTERNAL-REFS-TRACEABILITY.md](../EXTERNAL-REFS-TRACEABILITY.md).

> M0 shipped-surface inventory. Status: **Pass** / **Fix** / **Defer**.

## Summary

| Milestone | Items | Pass | Fix (this PR) | Defer |
|-----------|-------|------|---------------|-------|
| M0-B | 12 | 4 | 8 | 0 |
| M1 (partial) | 1 | 1 | 0 | 0 |
| M2 (partial) | 1 | 1 | 0 | 0 |
| M3 (partial) | 4 | 4 | 0 | 0 |
| M4 (partial) | 5 | 0 | 5 | 0 |
| M5 | 6 | 6 | 0 | 0 |

## Surface inventory

| Surface | Was | Now | Notes |
|---------|-----|-----|-------|
| Transcript | Fix | Pass | Response Card; console default; view toggles |
| Work | Fix | Pass | hook banner + side-by-side diff; plan ref links styled |
| Run | Fix | Pass | i18n run log; structured tool cards (duration/stdout) |
| Terminal | Fix | Pass | xterm.js; i18n hint |
| Preview | Fix | Pass | auto-probe + presets |
| Files editor | Fix | Pass | Monaco + git badge + path completion stub |
| Background tasks | Defer | Pass | full i18n via `useLocale` |
| RoomTaskBar | Fix | Pass | turn leads, 409 toast, lead help |
| Shortcuts ⌘6–⌘7 | Fix | Pass | `App.tsx` |
| Agent Response Card | — | Pass | P1c MVP |
| Inbox activity | Defer | Pass | segmented filter + NotificationCenter |
| Classic messenger | Defer | Pass | default `presentation="console"` |

## Fixes shipped (2026-06-14)

- `App.tsx`: workspace tabs 6–7 shortcuts
- `TranscriptViewOptions`: Human summary + peer channel toggles
- `RoomTaskBar`: turn lead history, lead `?` help, consensus complete 409 toast
- `RoomChat`: hook → Work routing (`isExecutionRelevantHook`)
- `AgentResponseCard` + `buildAgentResponseCard`
- `PlanExecutePanel`: `work-hook-alert` banner
- Terminal/Preview i18n keys
- M2: `agent_token` SSE (`room_sse_stream.py`), transcript stream preview, Run log tool cards
- M3: xterm terminal, preview auto-probe/presets, Monaco files editor, side-by-side Work diff
- M4: `make test-fast` / `ci-full`, bridge registry + `check_bridge_processes.py`, Settings diagnostics
- M4 follow-up: 17 slow modules → `integration` registry; `pytest-xdist` + `-n auto`; PR CI uses test-fast (~48s isolated / <2min target)
- M4 bridge stream: `bridge_stdout_parser.py` maps Cursor SDK deltas → `agent_token` / `tool_*` SSE during live turns
- M4 bridge stream (Codex): `parse_codex_json_event` + `codex_cli.on_bridge_event` → live `agent_token` / `tool_*`
- M4 bridge stream (Claude): `parse_claude_json_event` + `claude_cli` `stream-json` path → live `agent_token` / `tool_*`
- M6 partial: `RoomTaskBar` legacy `.room-task-bar__*` removed; canonical `.taskbar__*` only
- Handoff P1: `PlanProvenanceFooter`, cross-link footer, claimable rows, mode chip exclusivity, `sendReceiptLabel` locale
- M3 defer: Files `git_status` badge, composer `@` mention picker, Monaco path completion stub
- M1: Run log `toolCards` SSE + structured cards with duration/stdout

- M5: BackgroundTasksPanel + RunLogPanel i18n, inbox segment labels, plan ref link CSS, console default presentation, `test_i18n_messages_parity.py`

## Deferred (next)

- M6 (remainder): PlanExecutePanel / RoomChat / ChatBubble internal legacy class rename
- Rust hot-path (optional)

## QA gate

```bash
make test
cd web && npm run build
```

Manual: UI-HANDOFF §5 A–E, Transcript toggles, Work hook banner on `pre_execute` block (mock).
