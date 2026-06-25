# Mission OS — Operations

Run Agent Lab as a 24/7 local daemon with mission scheduler, gateway notify, and hybrid relay.

## Prerequisites

- Python venv at `agent-lab/.venv`
- Config: `~/.agent-lab/gateway.toml`, optional `~/.agent-lab/routes.toml`
- Env: copy `.env.example` → `.env` (never commit `.env`)

## Manual daemon

```bash
make dev   # foreground API + web for development
# or API-only daemon:
.venv/bin/python -m agent_lab.cli serve --daemon --host 127.0.0.1 --port 8765
```

`--daemon` sets `AGENT_LAB_MISSION_SCHEDULER=1` and starts a background cron thread.

## macOS launchd (recommended for 24/7)

```bash
make install-serve-daemon
```

Installs `com.agentlab.serve-daemon` to `~/Library/LaunchAgents/`.

Logs: `~/.agent-lab/logs/serve-daemon.{out,err}`

## Health checks

```bash
curl -s http://127.0.0.1:8765/api/health/daemon | jq .
curl -s http://127.0.0.1:8765/api/settings/gateway/ping -X POST
```

Settings UI: **Settings → Mission OS → Daemon status**

## Scheduler

- Schedules live in `run.json` → `schedules[]` per session
- Human pre-approve: `POST /api/sessions/{id}/schedules/{schedule_id}/approve`
- Manual tick (ops): `POST /api/mission-scheduler/tick?force=true`
- Optional hook token: set `AGENT_LAB_SCHEDULER_HOOK_TOKEN` and pass header `X-Agent-Lab-Scheduler-Token`

## Hybrid relay (PC off notify)

When daemon is offline, `fan_out_gateway_notify` POSTs to `gateway.toml` `[hybrid].relay_url`.

Deploy: [HYBRID-RELAY-WORKER.md](HYBRID-RELAY-WORKER.md)

## Trading launchd vs Mission OS

| Plist | Purpose |
|-------|---------|
| `com.agentlab.trading-*` | Quant trading mission (separate product) |
| `com.agentlab.serve-daemon` | Agent Lab API + mission scheduler |

Do not confuse trading triggers (`make install-mission-triggers`) with serve daemon.

## Tier D — Telegram merge ingress soak (live)

Validates **real** Cursor dry-run → `POST /api/gateway/telegram/webhook` with `/approve merge` → worktree merge (not pytest mocks).

```bash
AGENT_LAB_RUN_LIVE=1 make verify-ops-live-telegram-merge
# or without Tier A preflight:
AGENT_LAB_RUN_LIVE=1 SKIP_PREFLIGHT=1 make verify-ops-live-telegram-merge
```

Report: `sessions/_reports/live-telegram-merge-YYYY-MM-DD.json`

Requires `CURSOR_API_KEY` + bridge (same as Tier C). Telegram Bot API egress may fail with soak token — merge ingress is verified via HTTP webhook + execution status.

CI integration (Cursor stubbed): `tests/test_live_telegram_merge_soak.py::test_telegram_merge_ingress_webhook_integration`

## Tier E — tunnel + launchd soak (live)

Validates launchd serve daemon, `POST /api/hooks/mission-wake`, optional public tunnel URL, hybrid wake hints.

```bash
AGENT_LAB_RUN_LIVE=1 make verify-ops-live-tunnel-launchd
```

Report: `sessions/_reports/live-tunnel-launchd-YYYY-MM-DD.json`

Runbook: [TUNNEL-LAUNCHD-SOAK-RUNBOOK.md](TUNNEL-LAUNCHD-SOAK-RUNBOOK.md)

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Scheduler not ticking | `AGENT_LAB_MISSION_SCHEDULER=1`, daemon health `last_scheduler_tick_at` |
| Schedule skipped | `pre_approved_at` missing, cron/tz, `last_run_date` same day |
| Hybrid always fires | `AGENT_LAB_DAEMON_STALE_S`, PID in `~/.agent-lab/daemon_state.json` |
| Template hash mismatch | `gate_blocked` notify; fix template or re-approve plan |
