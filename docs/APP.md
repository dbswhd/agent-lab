# Agent Lab App

Desktop + web UI for AI development work → Cursor/Codex/Claude Room → `plan.md` → Human approval → worktree execute/merge → Oracle verify.

## Baseline before hybrid Rust work

Packaging snapshot and rollback instructions: [PACKAGING-BASELINE.md](./archive/legacy/PACKAGING-BASELINE.md)  
Hybrid rollout (Track 1 proceed / Track 2 conditional): [HYBRID-RUST-PYTHON-ADR.md](./HYBRID-RUST-PYTHON-ADR.md)  
Git tag: `baseline/pre-hybrid-rust-2026-06-28`

## Stack (vs quant-control)

| | quant-control | Agent Lab |
|---|---------------|-----------|
| Shell | Tauri 2 + Rust | **Tauri 2 + Rust** (same pattern) |
| UI | React 18 + Vite (1420) | React 18 + Vite (1420) |
| Backend | External pipeline HTTP 8878 | **Embedded FastAPI** on **8765** (spawned by Tauri) |
| Browser dev | — | `make dev` (5173 + 8765) |

quant-control reference: `~/Desktop/pipeline/apps/quant-control-app`

## Desktop app (installable)

**Prerequisites (dev):** Rust (`rustc`), Node 18+, Python 3.11+, `make install` once.

**Prerequisites (`.app` only):** Rust + Node for building once; end users need only the built `.app`.

```bash
cd ~/Projects/agent-lab
make install
cp .env.example .env   # AGENT_LAB_PROVIDER=codex + codex login
make tauri-dev         # native window (dev)
```

**Dev API ownership:** `make tauri-dev` sets `AGENT_LAB_SKIP_TAURI_API=1` — Vite [`ensure-dev-api.mjs`](../web/scripts/ensure-dev-api.mjs) spawns uvicorn on `:8765`; UI on `:1420` with `/api` proxy. Release `.app` uses Tauri `lib.rs` supervisor instead.

**Build `.app` / `.dmg` (macOS):**

```bash
make tauri-build
# Output: web/src-tauri/target/release/bundle/macos/Agent Lab.app
```

`make tauri-build` runs `scripts/prepare_bundled_runtime.sh` first and embeds a Python venv in the `.app` (no repo `make install` required on the target Mac).

The packaged app:

- Starts **uvicorn** on launch (port 8765)
- Stores sessions under `{repo}/sessions` (same for dev and packaged `.app`)
- Reads `.env` from `~/.agent-lab/.env`, else repo `~/Projects/agent-lab/.env`, else bundled `.env`
- Reads user paths from `~/.agent-lab/config.toml` (created on first API start if missing)
- Writes API logs to `~/Library/Logs/Agent Lab/agent-lab-api.log`

**Example `~/.agent-lab/config.toml`:**

```toml
[paths]
quant_pipeline = "/Users/you/Desktop/pipeline"

[api]
port = 8765

[logging]
dir = "/Users/you/Library/Logs/Agent Lab"
```

## Browser dev (optional)

```bash
make dev
# → http://127.0.0.1:5173
```

CLI still works:

```bash
python -m agent_lab run "주제"
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Backend status |
| GET | `/api/backends` | codex / openai / anthropic |
| GET | `/api/sessions` | List `sessions/*` |
| GET | `/api/sessions/{id}` | plan + transcript |
| POST | `/api/runs` | SSE stream, body `{ topic, backend? }` |

## Design handoff

This document is packaging/API guidance. Product positioning lives in [CONSOLE-PRODUCTIZATION.md](./CONSOLE-PRODUCTIZATION.md); current launch copy is **Human-in-the-loop agent development console**.

Legacy visual handoff references remain available for history:

→ **[docs/02-ui-ux-handoff.md](./02-ui-ux-handoff.md)** (iMessage / IG DM / Telegram 레퍼런스, 외주)  
→ **[docs/03-workflow.md](./03-workflow.md)** (단계별 사용 워크플로)

Quick map:

1. **Tokens** — `web/src/styles/tokens.css`
2. **Components** — `web/src/components/` (RunPanel, SessionList, SessionViewer)
3. **Layout** — `web/src/App.tsx`
4. **Do not** change API contracts without updating `web/src/api/client.ts`

## File layout

```
agent-lab/
├── app/server/main.py      # FastAPI
├── web/                    # Vite React
├── src/agent_lab/          # graph, runner, session, codex
├── scripts/dev.sh
├── Makefile
└── sessions/
```
