# Agent Lab stability (Phase 1–3)

Operational notes for API lifecycle, configuration, plan/execute validation, room preflight, CI, and release checks.

## API diagnostics

- **Health:** `GET /api/health?probe_bridge=true&probe_preflight=true` — per-agent readiness with CLI/bridge probes.
- **Preflight:** `GET /api/agents/preflight` — same structured `agents: [{ id, ready, reason, bridge_mode, … }]`.
- **Diagnostics:** `GET /api/diagnostics` — PID, uptime, port 8765 probe, resolved config paths, masked tool bins, last ~20 lines of boot log.

Boot log path (macOS, matches Tauri `web/src-tauri/src/lib.rs`):

`~/Library/Logs/Agent Lab/agent-lab-boot.log`

API log: same directory, `agent-lab-api.log`.

API startup uses FastAPI lifespan hooks. Startup diagnostics keep the same boot log behavior; shutdown is currently a no-op. Session detail loads still run stale worktree GC after reading `run.json`.

ops-P2 split FastAPI routes into `app/server/routers/*`; `app/server/main.py` is now app assembly only (1254 → 111 lines).

When the UI shows **API offline**, open diagnostics (sidebar) or call `/api/diagnostics` from curl. Retry: `make dev`, `make tauri-dev`, or restart the packaged app so Tauri spawns uvicorn again.

## Port 8765 policy (stale listener)

| Mode | Behavior |
|------|----------|
| **Dev** (`debug_assertions`) | If port 8765 is in use but `/api/health` fails, **do not** kill foreign processes. Stop the stale listener manually: `kill $(lsof -ti:8765)` then restart dev. |
| **Release** (Tauri) | If port is in use and health fails, Tauri may **stop only its own stale child** via `stop_process_on_port` before spawning a new uvicorn. |
| **Healthy reuse** | If health OK and `sessions_dir` matches, reuse the existing API (no second spawn). |

Never assume port 8765 belongs to Agent Lab without a successful health check.

## Configuration hierarchy

Applied in this order (explicit `os.environ` values win and are not overwritten):

1. `~/.agent-lab/.env` — API keys, `CODEX_BIN`, `CLAUDE_BIN`, `CURSOR_SDK_BRIDGE_BIN`, optional `AGENT_LAB_SESSIONS_DIR`
2. `~/.agent-lab/config.toml` — `[paths]`, `[api]`, `[logging]` (see `app_config.py`)
3. Repo `.env` or `DOTENV_PATH` — developer machine overrides (`app/server/main.py` after `apply_config_env()`)
4. `runtime_paths.configure_subprocess_path()` — PATH and bridge auto-fill when bins unset

**Sessions directory intent:** one shared folder for Tauri dev, Tauri release, and CLI. Set explicitly with `AGENT_LAB_SESSIONS_DIR` or `paths.sessions` in config.toml; otherwise derived from `paths.agent_lab` or repo defaults.

**Git:** Live runs under `sessions/*` are gitignored; only `sessions/_regression/` fixtures are tracked. Turn-state envelope sample lives in `tests/fixtures/`.

Template: see `.env.example` (absolute path section).

## Plan / execute after scribe

After scribe writes `plan.md`, the room emits SSE `plan_actions_validation` with issues such as:

- `missing_execute_section` — no `## 지금 실행` or legacy `## 다음에 할 일`
- `no_executable_now_action` — section present but no complete 3-field action
- `missing_roadmap_section` — multiple executable items without `## 실행 순서 (이후)`

Failures are logged; they do not block saving the plan. Scribe prompt prefers `## 지금 실행` + `## 실행 순서 (이후)` when the thread has actionable work.

Consensus auto-scribe may emit `consensus_dry_run_proposal` when a recommended action exists (UI gate in `RoomChat`).

## Room preflight and send gate

Before `POST /api/room/runs` (non–synthesize-only), the API runs lightweight probes for each selected agent:

| Agent | Probe |
|-------|--------|
| Cursor | Bridge ping; `CURSOR_SDK_BRIDGE_BIN` file exists (auto-launch) or external `CURSOR_SDK_BRIDGE_URL` |
| Codex | `codex --version` with subprocess `PATH` from `runtime_paths.configure_subprocess_path()` |
| Claude | `claude --version` |

If any agent is not ready, the API returns **400** with `detail.agents[]` (`id`, `reason`). The composer shows the same reasons inline.

Cursor bridge failures must include degraded fallback shape: `degraded`, `failure_code`, `fallback`, and `remediation`. CI fixture: `sessions/_regression/bridge_degraded_health/`. Governance fixtures: `objection_blocks_execute/`, `challenge_revises_metric/` (E-smoke).

**Phase I execute (worktree):** design and checklist in [`docs/EXECUTE-WORKTREE-REFORM.md`](EXECUTE-WORKTREE-REFORM.md) §11 — M0–M4 shipped; CI uses regression fixtures only (no live merge in Actions).

**Run lock:** `GET /api/room/run-lock`, `POST /api/room/runs/release-lock` (orphan/stale lock), `POST /api/room/runs/cancel` (cooperative stop). UI: **실행 잠금 해제** when a run appears stuck.

**SSE:** Worker failures emit `run_failed` then `error`. If the proxy disconnects without a terminal event, the client synthesizes `run_failed`.

**Long runs:** No default client timeout. Optional UI hint after `VITE_ROOM_LONG_RUN_HINT_MS` (default 180000 ms); cancel via **답변 중지** → `cancelRoomRun`.

**Full-team cost gate:** Composer shows estimated agent call count before send. Verify: analyze with 3 agents shows about 3 calls and sends without confirmation; `♾️` or `분업` with 3 agents disables send until the **~N회 호출 이해함** checkbox is checked.

**Cursor reconnect:** `POST /api/health/reconnect-cursor` — health panel **재연결** button.

## Phase 1 — Team coordination (tasks + channels)

Minimal CC Agent Teams–style coordination in the room:

| Piece | Storage | UI |
|-------|---------|-----|
| Shared task list | `run.json` → `tasks[]`, `team_lead` | **작업** bar above chat (`GET /api/sessions/{id}/tasks`) |
| Peer vs human chat | `chat.jsonl` → `visibility: human\|peer` | **동료 채널** toggle; peer lines styled and hidden by default |

**Tasks:** Agents can still write `[PROPOSED: …]` in discuss turns; titles are harvested into `tasks[]` after each turn (`room_tasks.sync_tasks_after_turn`). Claim API: `POST /api/sessions/{id}/tasks/{task_id}/claim` with `{ "agent": "cursor" }`.

**Peer channel:** Agent replies with `[이번 턴 · 동료 발화]` or explicit `visibility: peer` are filtered from the default transcript and chat scroll; a short system **peer digest** may be appended after R2+ saves.

## Phase 2 — Team coordination

Lead orchestration and pre-round assignment on top of Phase 1:

| Piece | Behavior |
|-------|----------|
| **Lead context** | `team_lead` (default `cursor`) gets the full task board in agent payload (`build_team_task_block`). Teammates see owned `pending`/`in_progress` tasks plus claimable unassigned items. |
| **Round-robin assign** | Before each room turn (`continue_room_round` / `run_room`), `assign_tasks_to_agents()` claims claimable tasks for non-lead agents; `run.json` is persisted early so assignments survive the turn write. |
| **Envelope consensus** | R2+ 자유 토론 / discuss: `consensus_reply_verdict` and `pick_anchor` prefer `agent-envelope` acts (`ENDORSE`, `AMEND`, …); plain `이의 없습니다` remains a fallback. |
| **Prompts** | `CONVERSATION_GUIDANCE` no longer asks agents to echo `[이번 턴 · 동료 발화]`; `[PROPOSED:]` is for new actionable work only (aligned with analysis-turn rules). |
| **API** | `PATCH /api/sessions/{id}/team-lead` with `{ "agent": "cursor" }` — optional lead change. |
| **UI** | **작업** bar shows `owner_agent`, **리드**, and a **청구 가능** subsection. |

**Verify:** Start a discuss turn with `[PROPOSED: …]` harvested tasks → refresh **작업** → send another turn and confirm owners rotate among non-lead agents. Consensus: agents reply with ` ```agent-envelope` ` `ENDORSE` fence; loop should treat as endorse without requiring exact `이의 없습니다` text.

## Phase 3 — Team coordination (board + execute + consensus)

| Piece | Behavior |
|-------|----------|
| **Plan links** | After each turn, task titles are matched to `## 지금 실행` 3-field actions (`plan_action_index` / `plan_action_id` on task). **plan #N** in **작업** bar opens the plan tab. |
| **Execute sync** | Human **approve** on plan execute marks linked tasks `completed` and records `execution:{id}` in `artifact_refs`. |
| **Task endorsements** | Envelope `ENDORSE`/`PASS` with `refs` matching task id/title/plan_action_id increments per-agent endorsements. |
| **Consensus gate** | Anchor consensus alone is not enough if open tasks lack endorsements from a majority of active agents (`consensus_incomplete`, reason `open_tasks`). Follow-up prompt lists open task ids. |
| **UI** | **작업** bar: lead `<select>`, ✓endorse counts, **완료** (manual), blocker banner when consensus tasks not ready. |
| **API** | `POST /api/sessions/{id}/tasks/{task_id}/complete` with optional `artifact_refs`. |

**Verify:** `[PROPOSED:]` → plan scribe aligns title → dry-run/approve execute → task shows **완료**. ♾️ consensus: agents ENDORSE with `refs: ["t-…"]` until blocker banner clears.

### Sprint D (turn lead UI, discuss task scope, provenance, receipts)

See **[SPRINT-D-CHECKLIST.md](./SPRINT-D-CHECKLIST.md)** for the full checkbox list.

| Piece | Behavior |
|-------|----------|
| **Turn lead UI** | `GET …/tasks` returns `turn_leads`; **작업** bar shows 이번 턴 리드 + T{n}→agent history. |
| **Discuss task scope** | Pure discuss: harvest `[PROPOSED:]` only — no `assign_tasks`, no `sync_tasks_plan_links`. |
| **Role guidance** | Lead vs teammate blocks in agent payload; lead discuss prepend. |
| **Plan provenance** | Scribe `(ref: chat.jsonl#Ln)`; `plan_provenance` in run.json when plan changes. |
| **Task complete gate** | Manual **완료** returns `409` when linked execution is `review_required` / `pending_approval` or `artifact_refs` execution unverified. |
| **Mode chip** | Composer shows 토론 / 정리·plan / 합의 + scribe timing hint. |
| **Clarifier** | `AGENT_LAB_CLARIFIER=1` — short topic / first message → `clarifier_prompt` SSE, agents skipped until Human elaborates. |
| **Turn receipt** | `send_receipt`: `discuss_saved` \| `plan_updated` \| `consensus_done` on `run.json` turns + SSE `complete`. |

**Verify:** discuss turn → tasks unlinked to plan; plan turn → refs in plan.md clickable; complete blocked until execute verified; `turn_leads` visible in task bar.

### Mailbox + server hooks (A/B/C)

| Piece | Behavior |
|-------|----------|
| **mailbox[]** | `run.json` → direct agent messages (`MESSAGE` envelope + `to`). **받은함** in **작업** bar; unread delivered in next agent payload. |
| **Hooks** | `~/.agent-lab/hooks.toml` or `.agent-lab/hooks.toml` — `task_completed`, `teammate_idle` shell commands (JSON stdin, exit 2 = block). |
| **Teammate idle** | After each agent in a round, optional peer `[idle gate · agent]` when in_progress tasks or hook feedback. |

Example: `.agent-lab/hooks.example.toml`, `scripts/hooks/verify-task.sh`.

### Phase E — objections (ROOM-REINFORCEMENT P0)

| Piece | Behavior |
|-------|----------|
| **objections[]** | plan 턴 harvest: envelope `BLOCK` / `CHALLENGE` + refs → `run.json`. |
| **Execute gate** | open BLOCK on `plan_action_index` → dry-run **409** `open_objection`. |
| **CHALLENGE** | open CHALLENGE + `task_id` → task `status: blocked`. |
| **♾️** | open objection → `consensus_incomplete` reason `open_objections`. |
| **API** | `POST …/objections/{id}/resolve` `{ verdict: accepted\|wontfix }`. |
| **UI** | 작업 바 미해결 이의 · 수용/기각. |

**Verify:** plan 턴 BLOCK → dry-run 409 → resolve → retry. **분업** profile → R1 Codex+Claude, R2 Cursor; context meta `capability_cwd` differs per agent. specialist/research Cursor R2 preview → `context_mode: artifact_only`, `peer_suppressed: true`, no R1 full agent body in `recent`. Rollback: `AGENT_LAB_F2_ARTIFACT_ONLY=0`.

### Phase F — asymmetric agents (P1)

| Piece | Behavior |
|-------|----------|
| **agent_capabilities** | `run.json` per-agent `tools`, `cwd_role`, `restrictions`. |
| **Specialist profile** | Composer **분업** · R1 codex+claude · R2 cursor · 2 rounds. |
| **Context** | `agent_workspace_lines` + `capability_preamble_block`; meta `capability_cwd`. |
| **F2 research** | `research_mode` or specialist → `harvest_artifacts_from_turn`; Cursor R2 uses `context_mode: artifact_only` (Human question + artifacts only). |
| **F4 health** | `/api/health?session_id=` adds `capability_label` / `capabilities` per agent row. |

### Phase G — artifacts & execute chain (P2)

| Piece | Behavior |
|-------|----------|
| **G1 artifacts[]** | plan/specialist/research turns harvest agent output → `run.json` + optional `artifacts/` files. |
| **G2 pre_execute** | `run_pre_execute_hooks` before dry-run snapshot; exit 2 → **409** `pre_execute_blocked`; `execution.pre_verify`. |
| **G3 delegate** | `DELEGATE agent: "…"` skips full parallel round; one agent + artifact + peer summary. |
| **UI** | Task bar artifacts list; plan panel pre_verify banner; session setup research toggle. |

**Verify:** specialist turn → `artifacts` in tasks API; delegate line → single agent reply; blocking `pre_execute` hook → dry-run 409.

### Phase E scribe (P1)

| Piece | Behavior |
|-------|----------|
| **E2 plan** | Scribe prompt includes objections, blocked indices, agent contributions. |
| **E2b discuss** | open objection + synthesize + discuss mode → scribe skip, patch `## 미해결 이의` only. |
| **E3 owner** | `[CHALLENGE · 반드시 응답]` block for task owner in payload. |

### Sprint C (human synthesis + per-turn lead + R1 order)

| Piece | Behavior |
|-------|----------|
| **Human 요약** | Chat toggle (default on): shows only **Human** messages + `[human synthesis — 턴 요약]` system lines; agent bubbles hidden. |
| **Per-turn lead** | `GO cursor` / `리드: codex` in user message sets lead; else rotate by human-turn index. Persisted in `run.json` `turn_leads` + `team_lead`. |
| **R1 order** | Teammates run in parallel first; **lead runs last** with full thread including peer replies. |
| **Discuss policy** | Pure discuss turns harvest `[PROPOSED:]` tasks but **skip** `assign_tasks_to_agents` (no pre-claim). |
| **Claim hints** | Teammates see claimable task ids in `build_team_task_block`; synthesis appended on session save. |

**Verify:** discuss turn → tasks appear unassigned; `GO codex` → lead badge; R1 transcript order codex/claude before cursor; end of turn → **턴 요약** line; **Human 요약** hides agent bubbles.

### Sprint B (plan snapshot + task lifecycle + harvest cap)

| Piece | Behavior |
|-------|----------|
| **pending_plans[]** | First dry-run per `action_key` + current `plan_hash` requires Human approval of frozen snapshot (`409 plan_snapshot_required`). |
| **API** | `GET .../execute/pending-plans`, `POST .../pending-plans/{id}/approve\|reject`. |
| **Task lifecycle** | dry-run start → linked task `in_progress`; execute reject → `pending`; approve (verified) → `completed`. |
| **Harvest cap** | `AGENT_LAB_MAX_TASKS_PER_TURN` (default **8**) limits new tasks per turn from `[PROPOSED:]` / `turn_state`. |

### Sprint A (consensus + execute gates + task UX)

| Piece | Behavior |
|-------|----------|
| **ENDORSE + `[PROPOSED:]`** | `classify_consensus_reply` treats body `[PROPOSED: …]` as **substantive** even when `act: ENDORSE` or plain `이의 없습니다`. |
| **Task complete gate** | Linked tasks auto-complete on Human approve only when execution status is **completed** (not `review_required`). Manual **완료** blocked while matching execution is `pending_approval` / `review_required`. |
| **Cross-links** | **작업** `plan #N` → plan tab + scroll to action card; plan panel **연결 작업** → chat task row. |

## Codex room sandbox

Room turns use Codex CLI in a **read-only** workspace sandbox by default (debate / verify, not full edits).

| Variable | Effect |
|----------|--------|
| `CODEX_ROOM_WORKSPACE_WRITE=1` | Allow writes in the room workspace (use only when the turn must edit files). |
| `CODEX_BIN` | Absolute path when GUI `PATH` lacks `codex`. |

**os error 2** (missing file/path) is mapped to a Korean hint in API/UI responses; check workspace binding and sandbox before enabling writes.

## Room CLI retry and partial turns

Claude/Codex subscription CLI calls share the same transient retry policy for Room use.

| Variable | Effect |
|----------|--------|
| `AGENT_LAB_CLI_RETRY_MAX` | Max attempts for retryable CLI failures (default `3`). |
| `AGENT_LAB_CLI_RETRY_BASE_SEC` | Exponential backoff base delay in seconds (default `2`). |
| `AGENT_LAB_CLI_RETRY_ROOM_ONLY=1` | Apply CLI retry only to room turns; non-room calls attempt once. |

Retryable: `429`, rate limit, timeout/timed out, connection refused, temporarily unavailable, overloaded, exit 52. Non-retryable: auth/credit balance, invalid API key, permission denied, empty output.

General discuss/plan turns now store `status: partial` when at least one agent succeeds and at least one agent fails. Successful replies remain in chat and can feed the scribe. If all agents fail the turn is `failed`; cancelled runs remain `cancelled`. Consensus ENDORSE loops stay strict: an agent failure stops consensus instead of counting as partial agreement.

## Phase 3 — CI, regression pyramid, release

### Regression test pyramid (mock-only in CI)

| Layer | What | How |
|-------|------|-----|
| Unit / API | `tests/test_*.py` | `pytest tests/ -q` — no live LLM, no secrets |
| Tauri paths | `tests/test_tauri_config.py` | `frontendDist` → `web/dist`; bundle `resources` → `runtime/web/dist`, `runtime/venv` |
| Room fixtures | `sessions/_regression/*` (14 smoke baselines via `scripts/smoke_room.py`) | `tests/test_regression_baselines.py`, `tests/test_smoke_room_governance.py`, `scripts/smoke_room.py` |
| Score / guards | regression fixtures + execute worktrees | `scripts/score_session.py --json`, `scripts/check_worktree_orphans.py` |
| Mock E2E | `scripts/smoke_room_e2e.py` | `tests/test_smoke_room_e2e.py`, `AGENT_LAB_MOCK_AGENTS=1` |

`scripts/smoke_room.py` is also runnable locally; use **`--api`** only when uvicorn is already on `:8765`. Treat full room scripts as **nightly / manual** when they need a live API or real CLIs — CI uses pytest wrappers only.

### GitHub Actions (`.github/workflows/ci.yml`)

**Every PR / push (`test` job, ubuntu):**

- `pip install -e ".[cursor]"` → `pytest tests/ -q`
- `scripts/smoke_room.py` (14 regression baselines), `scripts/check_worktree_orphans.py`, `scripts/score_session.py --json` on regression fixtures
- `cd web && npm ci && npm run build`
- `cd web/src-tauri && cargo check`

**Nightly / manual (`nightly-bundle`, macos, `continue-on-error`):**

- `make prepare-bundled-runtime`
- Bundled venv: `import app.server.main`, `cursor-sdk-bridge` present
- Does **not** build DMG (use `make tauri-build` locally if packaging)

Trigger nightly: Actions → **ci** → **Run workflow**, or wait for schedule (`0 6 * * *` UTC).

### Release verification

After `make tauri-build` (or with a custom `.app` path):

```bash
make verify-release
# or: ./scripts/verify_release.sh "/path/to/Agent Lab.app"
```

Checks:

1. Bundled `runtime/venv` Python imports `app.server.main`
2. `cursor-sdk-bridge` (or `cursor_sdk` vendor launcher) in bundle
3. `runtime/web/dist` exists
4. If API is up: `GET /api/health`, `GET /api/sessions`

Skip live API when the app is not running:

```bash
VERIFY_RELEASE_SKIP_API=1 make verify-release
```

## Phase H — Scribe summaries & session score

| Piece | Behavior |
|-------|----------|
| **H1 Scribe input** | `synthesize_plan()` feeds per-agent diff summaries (`room_scribe_enrichment.py`), not full verbatim re-debate; fallback to trimmed numbered thread when no agent replies. Plan enrichment still adds `## 에이전트별 기여 (자동)` / `## 미해결 이의`. |
| **H4 KPI** | `python scripts/score_session.py <session-folder>` — objection resolution, execute first-try, merge/worktree KPIs, partial turn rate, plan ref validity, duplicate speech (offline; exit 1 only on bad args). `--json` for machine output. |
| **Execute worktree guard** | `python scripts/check_worktree_orphans.py` — fails CI on orphan or terminal execute worktree dirs; pending approval worktrees are allowed. |

```bash
python scripts/score_session.py sessions/<session-id>
# or: make score-session SESSION=...
```

## Manual verification

```bash
curl -s http://127.0.0.1:8765/api/diagnostics | python3 -m json.tool
curl -s 'http://127.0.0.1:8765/api/health?probe_bridge=true&probe_preflight=true' | python3 -m json.tool
curl -s http://127.0.0.1:8765/api/agents/preflight | python3 -m json.tool
pytest tests/ -q
cd web && npm run build
```

**UI (수동):**

1. 사이드바 에이전트 상태 — Cursor **external bridge** vs **auto-launch**, **재연결** 동작 확인.
2. Codex/Claude 미설치 시 composer 상단 preflight 경고 및 전송 차단 확인.
3. 실행 중 3분 후「장시간 실행 중」+ 답변 중지; stuck 시「실행 잠금 해제」.
