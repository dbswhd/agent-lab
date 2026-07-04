# Structure refactor — execute wave (2026-06)

> **Metrics baseline:** [STRUCTURE-METRICS.md](./STRUCTURE-METRICS.md) · **Room package:** [ROOM-PACKAGE-REFACTOR-DESIGN.md](./ROOM-PACKAGE-REFACTOR-DESIGN.md)

Agreed execute order for **구조 점검** scope. Items explicitly **out of scope** for this wave are listed at the bottom.

---

## Execute order

```text
Wave A — RoomChat.tsx vertical split ✅
Wave B — room/context/ concern split ✅
Wave C — live_* / pipeline_* soak & spike → scripts/
Wave D — turn_flow.py additional thinning ✅
```

### Wave A — `RoomChat.tsx` (~4557 LOC)

Split without changing UX contract:

| Extract | Responsibility |
|---------|----------------|
| `useRoomSseHandler` (hook) | `runRoom()` callback, `patchTurnMessages`, session bind / pending→real id |
| `RoomTranscriptPanel` | message list, console presentation, markers |
| `RoomChat` (shell) | workbench layout, inspector, props wiring |

**Keep:** `useSessionRunState`, `runSessionRegistry`, `ChatComposer`, `runRoom` + `consumeSse()` (no raw `EventSource`).

**Tests:** `tests/test_workspace_ui_contract.py` — re-point token assertions or keep thin re-exports; run after each slice.

**Baseline:** `make structure-metrics-check` after intentional LOC drop.

### Wave B — `room/context/` package ✅

Split into submodules under `room/context/` with **`__init__.py` re-export facade** (no import churn). Monolithic `room/context.py` removed.

| Module | Contents |
|--------|----------|
| `constraints.py` | `build_constraints_block`, guidance constants, gate patterns |
| `peer_digest.py` | `collect_peer_messages`, `format_peer_block`, … |
| `plan_excerpt.py` | `extract_agreed_bullets`, `build_plan_open_block`, … |
| `message_trim.py` | `prepare_recent_messages`, trim/cap helpers |

**Out of this wave:** `repo_tree_context.py` / `context/bundle.py` repo-tree assembly (already separate).

**Tests:** `tests/test_room_context.py`, `tests/test_room_context_compact.py`.

### Wave C — root soak / spike cleanup ✅

Implementation lives under **`scripts/soak/`**; thin backward-compatible shims remain at `src/agent_lab/live_*.py` until grep-clean.

| Shim (`src/agent_lab/`) | Implementation |
|-------------------------|----------------|
| `live_execute_spike.py` | `scripts/soak/live_execute_spike.py` |
| `live_telegram_merge_soak.py` | `scripts/soak/live_telegram_merge_soak.py` |
| `live_tunnel_launchd_soak.py` | `scripts/soak/live_tunnel_launchd_soak.py` |

CLI wrappers (`scripts/live_*.py`) import from `scripts.soak.*`.

**Defer:** `pipeline_market_read.py`, `pipeline_research_read.py` — wide test/MCP import surface; separate wave if moved under `trading_mission/` or `research/`.

### Wave D — `turn_flow.py` thinning ✅

Extract helpers; keep `run_room` / `continue_room_round` as thin orchestration shells (scribe · verified-loop · goal-auto-continue branching stays here).

| Module | Contents |
|--------|----------|
| `turn_flow_support.py` | checkpoint, budget emit, divergence options, stage routing |
| `turn_flow_setup.py` | turn profile flags, server clarifier interview |
| `turn_flow_rounds.py` | clarifier / delegate / consensus / parallel dispatch |
| `turn_flow_finalize.py` | post-turn auto-scribe tail, SSE `complete` event |
| `turn_flow.py` | entry points + verified/goal continuation recursion |

**Tests:** `tests/test_room_turn_flow.py`, `tests/test_token_efficiency.py`, `tests/test_divergence_profile.py`.

---

## Out of scope (this wave)

| Item | Reason |
|------|--------|
| **Repo tree** | Already `repo_tree_context.py` + `context/bundle.py` |
| **Gateway** | Already `src/agent_lab/gateway/` subpackage |
| **trading / extensions migration** | `extensions/quant_trading.py` delegation exists; `trading_mission/` is separate subpackage |
| **`turn_flow.py` thinning** | **Wave D** ✅ — helpers in `turn_flow_*.py`; entry points unchanged |

---

## Session artifacts

- **This wave topic:** structure refactor (A–C above) in active session `plan.md`
- **Trading Mission:** separate session or `docs/trading-mission/` + scheduler artifacts — not mixed into structure plan

---

## Verification (each wave)

```bash
make test-fast
pytest tests/test_workspace_ui_contract.py -q
make audit-room-imports
make structure-metrics-check   # after baseline update
python scripts/smoke_room.py   # optional E2E
```
