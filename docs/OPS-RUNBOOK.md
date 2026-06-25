# Agent Lab Ops Runbook

Manual operations checks are split into tiers so CI-safe regression checks and live Cursor SDK checks stay separate.

## P0 UI baseline — browser and Tauri are separate

The automated browser smoke owns DOM assertions and baseline screenshots. It starts an
isolated API/Vite pair against `sessions/_regression/ui_pending_diff`, then checks the
session → plan → pending dry-run diff path.

```bash
make smoke-web-ui
```

Artifacts are written to `/tmp/agent-lab-ui-smoke/web/` by default. Override that with
`AGENT_LAB_UI_ARTIFACT_DIR=/path/to/output`.

The Tauri smoke is a separate, interactive real-window scenario. It validates the same
read-only fixture and API contract, launches the actual macOS Tauri window, and asks the
operator to confirm session selection → `plan · 승인` → open `로컬 diff` containing
`P0_UI_DIFF_MARKER`.

```bash
make smoke-tauri-ui
```

This target intentionally stays out of `make ci`: macOS WebKit does not provide the DOM
automation path used by the browser smoke, and the real-window check requires operator
confirmation. Use `AGENT_LAB_TAURI_UI_SMOKE_LAUNCH_ONLY=1 make smoke-tauri-ui` only to
verify launch/window/API wiring; it does not count as visual confirmation.

Both targets require ports `8765` and their frontend port (`5173` or `1420`) to be free.
Neither target performs a real dry-run or mutates a user session.

## Tier A — PR and weekly baseline

Use Tier A for every PR before merge and for weekly local checks.

```bash
make verify-ops
```

This runs regression CI, checks execute worktree orphans, writes weekly JSON/Markdown artifacts, and prints:

```text
Ops report: sessions/_reports/weekly-YYYY-MM-DD.md
```

The weekly Markdown includes **Last live checks** from the newest `live-worktree-*.json` and `live-merge-*.json` files in `sessions/_reports/`.

Useful variants:

| Command | Use |
|---------|-----|
| `make verify-ops REPORT=0` | Fast CI-safe check without writing a weekly artifact. |
| `make verify-ops INCLUDE_FIXTURES=1 DAYS=30` | Offline demo report that includes regression fixtures. |
| `STRICT=1 make verify-ops INCLUDE_FIXTURES=1` | Fail with exit 2 when M4 milestones fail. |

## Tier B — live worktree verification

Use Tier B monthly, after execute/worktree changes, or after Cursor bridge updates. It performs one real Cursor SDK dry-run in a disposable git repo and rejects the execution, so no merge occurs.

Precondition: Tier A is green.

```bash
AGENT_LAB_RUN_LIVE=1 make verify-ops-live
```

The target runs Tier A preflight with `REPORT=0` unless `SKIP_PREFLIGHT=1` is set, then writes:

```text
Live ops report: sessions/_reports/live-worktree-YYYY-MM-DD.json (GO)
```

Use this only on a machine with `CURSOR_API_KEY` and a working bridge. It is intentionally not part of GitHub Actions.

```bash
AGENT_LAB_RUN_LIVE=1 SKIP_PREFLIGHT=1 make verify-ops-live
```

### Go / No-Go

| Check | GO means |
|-------|----------|
| Preflight | Cursor SDK/bridge is ready or the live script records an intentional skip. |
| Main clean | The disposable base repo stays clean after dry-run and reject. |
| Worktree isolation | Dry-run executes from the isolated worktree git root. |
| Worktree discard | Reject removes the execution worktree. |

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | GO |
| 1 | Usage or missing `AGENT_LAB_RUN_LIVE=1` guard |
| 2 | NO_GO |
| 3 | SKIPPED, usually missing key/bridge or `AGENT_LAB_SKIP_LIVE=1` |

## Tier C — live merge

Use Tier C after Tier B returns GO, after execute/merge code changes, or once per branch cut. It runs one live dry-run in the same kind of disposable git repo, approves the pending execution, and verifies the merge commit on the disposable base branch.

```bash
AGENT_LAB_RUN_LIVE=1 make verify-ops-live-merge
```

The target runs Tier A preflight with `REPORT=0` unless `SKIP_PREFLIGHT=1` is set, then writes:

```text
Live merge ops report: sessions/_reports/live-merge-YYYY-MM-DD.json (GO)
```

Rollback instructions and the operator prompt are in [LIVE-MERGE-OPERATOR.md](LIVE-MERGE-OPERATOR.md).

## Tier D — live Telegram merge ingress

Use Tier D after gateway/Telegram ingress changes. Validates real Cursor dry-run → Telegram webhook `/approve merge` → disposable repo merge.

```bash
AGENT_LAB_RUN_LIVE=1 make verify-ops-live-telegram-merge
```

Report: `sessions/_reports/live-telegram-merge-YYYY-MM-DD.json`

See [MISSION-OS-OPS.md](MISSION-OS-OPS.md) §Tier D.

## Tier E — tunnel + launchd soak

Use Tier E after `make install-serve-daemon`, hybrid wake URL changes, or monthly 24/7 ops checks. Validates daemon health, local/tunnel `mission-wake`, and hybrid wake hints. Does not call Cursor SDK.

```bash
export AGENT_LAB_SCHEDULER_HOOK_TOKEN='…'
export AGENT_LAB_TUNNEL_WAKE_URL='https://your-tunnel.example'   # optional
AGENT_LAB_RUN_LIVE=1 make verify-ops-live-tunnel-launchd
```

Report: `sessions/_reports/live-tunnel-launchd-YYYY-MM-DD.json`

Operator steps: [TUNNEL-LAUNCHD-SOAK-RUNBOOK.md](TUNNEL-LAUNCHD-SOAK-RUNBOOK.md)

CI integration: `tests/test_live_tunnel_launchd_soak.py::test_tunnel_launchd_soak_integration`

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Bridge degraded | Check `/api/health?probe_bridge=true`; use the health panel reconnect action. |
| Exit 1 | Export `AGENT_LAB_RUN_LIVE=1` and rerun. |
| Exit 2 | Treat as NO_GO; inspect `sessions/_reports/live-worktree-YYYY-MM-DD.json`. |
| Exit 3 | Check `CURSOR_API_KEY`, bridge setup, or `AGENT_LAB_SKIP_LIVE`. |
| Weekly artifact missing | `REPORT=0` skips Tier A artifact writes by design. |
| Live merge artifact missing | Check `sessions/_reports/live-merge-YYYY-MM-DD.json`; Tier C writes only when the live script starts. |

## Mission OS daemon

Run Agent Lab as a 24/7 local daemon with mission scheduler, gateway notify, and hybrid relay.

**Prerequisites:** Python venv at `agent-lab/.venv` · Config `~/.agent-lab/gateway.toml` · Copy `.env.example` → `.env`

```bash
make dev   # foreground API + web (dev)
# API-only daemon:
.venv/bin/python -m agent_lab.cli serve --daemon --host 127.0.0.1 --port 8765
```

**macOS launchd (24/7 권장):**
```bash
make install-serve-daemon   # ~/Library/LaunchAgents/com.agentlab.serve-daemon
```
Logs: `~/.agent-lab/logs/serve-daemon.{out,err}`

**Health checks:**
```bash
curl -s http://127.0.0.1:8765/api/health/daemon | jq .
curl -s http://127.0.0.1:8765/api/settings/gateway/ping -X POST
```

**Scheduler ops:**
- 스케줄: `run.json` → `schedules[]` per session
- 승인: `POST /api/sessions/{id}/schedules/{schedule_id}/approve`
- 수동 tick: `POST /api/mission-scheduler/tick?force=true`

**Troubleshooting:**

| 증상 | 확인 |
|------|------|
| Scheduler not ticking | `AGENT_LAB_MISSION_SCHEDULER=1`, daemon `last_scheduler_tick_at` |
| Schedule skipped | `pre_approved_at` 없음, cron/tz, `last_run_date` 동일일 |
| Hybrid always fires | `AGENT_LAB_DAEMON_STALE_S`, `~/.agent-lab/daemon_state.json` PID |
| Template hash mismatch | `gate_blocked` notify; 템플릿 수정 또는 plan 재승인 |

Hybrid relay (daemon offline 시): `fan_out_gateway_notify` → `gateway.toml [hybrid].relay_url`. 배포: [HYBRID-RELAY-WORKER.md](HYBRID-RELAY-WORKER.md)

---

## Mission dogfood

Mock 스모크는 FSM 스냅샷만 검증. 실 사용 품질은 한 건의 live/mock 미션을 끝까지 돌린 뒤 점검.

**Mock dogfood (CI-safe):**
```bash
make mission-dogfood-run   # plan gate → pause/resume → verify PASS → MISSION_DONE
```

**KPI 캡처:**
```bash
LATEST=$(ls -t sessions | grep -v '^_' | grep -v '^dogfood' | head -1)
make score-session SESSION=sessions/$LATEST
python scripts/mission_dogfood_report.py sessions/$LATEST
```

**Weekly routine:**
```bash
make mission-dogfood-weekly       # mock dogfood + score-weekly
make mission-dogfood-weekly SKIP_MOCK=1   # weekly rollup only
make score-weekly                 # standalone H4 weekly ops report
```

**Live 미션 KPI 기대치:**

| 항목 | 기대 |
|------|------|
| `mission_loop.repair_events` | verify FAIL 시만 증가; cap 미만 |
| `mission_loop.notepad_chars` | `learnings.md` 등 회고·검증 기록 > 200 chars |
| `mission_circuit_breaker` | 정상 완료 시 0 |
| `mission_completed` | `MISSION_DONE` 시 100% |

**Notepad 품질 (수동):**
- [ ] `verification.md` — 마지막 verify verdict·명령 요약
- [ ] `learnings.md` — 실패 원인·다음 시도와 중복 없음
- [ ] `decisions.md` — Human gate·BLOCK 해소 기록

**회귀:**
```bash
make smoke              # 32 baselines incl. mission_loop_*
make test -k mission_loop
```

---

## Related docs

- [Live Cursor worktree dry-run](LIVE-CURSOR-WORKTREE-DRY-RUN.md)
- [Live worktree merge operator](LIVE-MERGE-OPERATOR.md)
- [Hybrid relay worker](HYBRID-RELAY-WORKER.md)
- [Stability notes](STABILITY.md)
