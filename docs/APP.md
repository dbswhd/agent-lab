# Agent Lab App

Desktop + web UI for topic → Planner → Critic → Scribe → `sessions/`.

## Stack (vs quant-control)

| | quant-control | Agent Lab |
|---|---------------|-----------|
| Shell | Tauri 2 + Rust | **Tauri 2 + Rust** (same pattern) |
| UI | React 18 + Vite (1420) | React 18 + Vite (1420) |
| Backend | External pipeline HTTP 8878 | **Embedded FastAPI** on **8765** (spawned by Tauri) |
| Browser dev | — | `make dev` (5173 + 8765) |

quant-control reference: `~/Desktop/pipeline/apps/quant-control-app`

## Desktop app (installable)

**Prerequisites:** Rust (`rustc`), Node 18+, Python 3.11+, `make install` once.

```bash
cd ~/Projects/agent-lab
make install
cp .env.example .env   # AGENT_LAB_PROVIDER=codex + codex login
make tauri-dev         # native window (dev)
```

**Build `.app` / `.dmg` (macOS):**

```bash
make tauri-build
# Output: web/src-tauri/target/release/bundle/macos/Agent Lab.app
```

The packaged app:

- Starts **uvicorn** on launch (port 8765)
- Stores sessions under `~/Library/Application Support/com.yoonjong.agentlab/sessions`
- Reads `.env` from repo `~/Projects/agent-lab/.env` if present, else `~/.agent-lab/.env`

**Note:** The `.app` still needs Python deps (`make install` in the repo) or a working `python3` with `agent-lab` installed until we add a bundled runtime.

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

Visual polish is **intentionally minimal**. Full brief for outsourcing:

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
