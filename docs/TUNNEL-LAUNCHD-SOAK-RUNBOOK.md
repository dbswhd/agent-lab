# Tunnel + launchd soak runbook (Tier E)

Validates **24/7 Mission OS ops**: macOS launchd serve daemon, local `mission-wake` hook, optional public tunnel (cloudflared/ngrok), and hybrid relay wake hints.

Does **not** call Cursor SDK (unlike Tier B/C/D).

## When to run

| Trigger | Command |
|---------|---------|
| After `make install-serve-daemon` | Tier E soak |
| After hybrid wake / tunnel URL change | Tier E with `AGENT_LAB_TUNNEL_WAKE_URL` |
| Monthly ops cadence | `make verify-ops-live-tunnel-launchd` |
| After gateway / scheduler hook changes | Tier E |

## Prerequisites

1. Python venv + `.env` (see `.env.example`)
2. `AGENT_LAB_SCHEDULER_HOOK_TOKEN` set locally and in Worker/tunnel client
3. API listening on `127.0.0.1:8765` via launchd or foreground daemon:

```bash
make install-serve-daemon
# or
.venv/bin/python -m agent_lab.cli serve --daemon --host 127.0.0.1 --port 8765
```

4. Optional tunnel — expose local API:

```bash
# cloudflared quick tunnel (example)
cloudflared tunnel --url http://127.0.0.1:8765
# copy https://….trycloudflare.com → AGENT_LAB_TUNNEL_WAKE_URL
```

5. `~/.agent-lab/gateway.toml` hybrid section (Worker parity):

```toml
[hybrid]
enabled = true
relay_url = "https://your-worker.example/relay"
wake_url = "https://your-tunnel.example/api/hooks/mission-wake"
wake_enabled = true
```

See [HYBRID-RELAY-WORKER.md](HYBRID-RELAY-WORKER.md).

## Tier E — automated soak

```bash
export AGENT_LAB_SCHEDULER_HOOK_TOKEN='your-token'
export AGENT_LAB_TUNNEL_WAKE_URL='https://your-tunnel.example'   # optional but recommended

AGENT_LAB_RUN_LIVE=1 make verify-ops-live-tunnel-launchd
```

Report:

```text
sessions/_reports/live-tunnel-launchd-YYYY-MM-DD.json
```

Fast path (skip Tier A preflight):

```bash
AGENT_LAB_RUN_LIVE=1 SKIP_PREFLIGHT=1 make verify-ops-live-tunnel-launchd
```

Manual CLI:

```bash
AGENT_LAB_RUN_LIVE=1 .venv/bin/python scripts/live_tunnel_launchd_soak.py --json
```

### Go / No-Go

| Check | GO means |
|-------|----------|
| `daemon_health_ok` | `GET /api/health/daemon` returns 200 |
| `daemon_scheduler_enabled` | `scheduler_enabled: true` in daemon state |
| `local_mission_wake_ok` | `POST /api/hooks/mission-wake` → `{ ok: true, wake: true }` |
| `scheduler_tick_updated` | Wake accepted; tick timestamp advanced or wake body ok |
| `hybrid_wake_hint_ok` | Offline relay envelope includes `wake.url` |
| `launchd_loaded` | **warn-only** unless `--require-launchd` |
| `tunnel_wake_ok` | Required only when `AGENT_LAB_TUNNEL_WAKE_URL` is set |

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | GO |
| 1 | Usage / missing `AGENT_LAB_RUN_LIVE=1` |
| 2 | NO_GO |
| 3 | SKIPPED (API offline or `AGENT_LAB_SKIP_LIVE=1`) |

## Manual verification (operator)

### 1. launchd

```bash
launchctl print "gui/$(id -u)/com.agentlab.serve-daemon"
tail -f ~/.agent-lab/logs/serve-daemon.err
```

### 2. Daemon health

```bash
curl -s http://127.0.0.1:8765/api/health/daemon | jq .
```

### 3. Local wake

```bash
curl -X POST http://127.0.0.1:8765/api/hooks/mission-wake \
  -H "Content-Type: application/json" \
  -H "X-Agent-Lab-Scheduler-Token: $AGENT_LAB_SCHEDULER_HOOK_TOKEN" \
  -d '{}'
```

### 4. Tunnel wake (PC asleep simulation)

From a **different network** (phone hotspot / VPS):

```bash
curl -X POST "https://your-tunnel.example/api/hooks/mission-wake" \
  -H "Content-Type: application/json" \
  -H "X-Agent-Lab-Scheduler-Token: $AGENT_LAB_SCHEDULER_HOOK_TOKEN" \
  -d '{}'
```

### 5. Hybrid Worker wake parity

Worker POST relay when daemon offline → reads `envelope.wake` → POST tunnel URL.

Test locally with [docs/examples/hybrid-relay-worker.js](examples/hybrid-relay-worker.js).

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `daemon health unavailable` | `make install-serve-daemon`; check port 8765 |
| mission-wake 401 | Set matching `AGENT_LAB_SCHEDULER_HOOK_TOKEN` |
| tunnel_wake_ok FAIL | Tunnel not running; URL must reach local API |
| launchd not loaded | `make install-serve-daemon`; check plist paths |
| tick timestamp unchanged | No due schedules — wake still OK if HTTP 200 |

## CI integration

Mock-safe hook + relay test (no live tunnel):

```bash
pytest tests/test_live_tunnel_launchd_soak.py::test_tunnel_launchd_soak_integration -q
```

## Related

- [MISSION-OS-OPS.md](MISSION-OS-OPS.md)
- [OPS-RUNBOOK.md](OPS-RUNBOOK.md) — Tier A–E matrix
- [HYBRID-RELAY-WORKER.md](HYBRID-RELAY-WORKER.md)
