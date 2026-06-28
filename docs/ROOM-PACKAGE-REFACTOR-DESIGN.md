# Room package refactor design

Design artifact for wave 1. **No file moves in this wave** — import graph, public API, and shim strategy only.

Target: move `room_*.py` → `src/agent_lab/room/` following the `runtime/` subpackage pattern, while keeping existing import paths working.

## Scope

| Item | Count |
|------|------:|
| `room_*.py` modules at root | 28 |
| Facade | `room.py` (stays at root in wave 2+) |
| Modules with dedicated tests | 22 test files under `tests/test_room_*.py` |

Regenerate the live graph:

```bash
python scripts/room_import_graph.py
python scripts/room_import_graph.py --json
```

## Proposed layout (wave 2)

```
src/agent_lab/
  room.py                    # public facade (unchanged path)
  room/
    __init__.py              # optional: re-exports for agent_lab.room.* subpaths
    messages.py              # was room_messages.py
    turn_flow.py             # was room_turn_flow.py
    ...
```

**Backward-compatible shims** at the old paths during transition:

```python
# src/agent_lab/room_messages.py (shim, delete after migration)
from agent_lab.room.messages import *  # noqa: F403
```

Prefer thin shims over breaking imports. Remove shims only after grep shows zero external `agent_lab.room_*` imports.

## Layer model (from import graph)

```mermaid
flowchart TB
  subgraph facade["Facade"]
    room["room.py"]
  end
  subgraph orchestration["Orchestration"]
    turn_flow["room_turn_flow"]
    turn_meta["room_turn_meta"]
    parallel["room_parallel_rounds"]
    consensus_r["room_consensus_rounds"]
    session_p["room_session_persist"]
  end
  subgraph invoke["Agent invoke / stream"]
    invoke["room_agent_invoke"]
    sse["room_sse_stream"]
    dispatch["room_dispatch"]
    delegate["room_delegate"]
  end
  subgraph domain["Domain state"]
    messages["room_messages"]
    context["room_context"]
    consensus["room_consensus"]
    turn_state["room_turn_state"]
    tasks["room_tasks"]
    objections["room_objections"]
    mailbox["room_mailbox"]
    artifacts["room_artifacts"]
  end
  subgraph policy["Policy / hooks"]
    hooks["room_hooks"]
    preset["room_preset"]
    capabilities["room_agent_capabilities"]
    team["room_team_orchestration"]
  end
  subgraph leaf["Leaf / auxiliary"]
    plan_scribe["room_plan_scribe"]
    scribe_enrich["room_scribe_enrichment"]
    retry["room_retry"]
    live_log["room_live_log"]
    chat_ch["room_chat_channels"]
    dispatch_i["room_dispatch_intents"]
    models_cfg["room_models_config"]
  end

  room --> orchestration
  room --> invoke
  orchestration --> invoke
  orchestration --> domain
  orchestration --> policy
  invoke --> domain
  invoke --> policy
  domain --> leaf
  policy --> domain
```

### Leaf modules (no in-package imports)

Moved to `agent_lab.room.*` in wave 2b (root shims retained):

- `room.delegate` (was `room_delegate.py`)
- `room.models_config` (was `room_models_config.py`)
- `room.retry` (was `room_retry.py`)

Facade lives in `agent_lab/room/__init__.py` (replaces root `room.py`; Python cannot load both a `room.py` module and `room/` package).

### Hub modules (≥5 outgoing in-package edges)

| Module | Out edges | Notes |
|--------|----------:|-------|
| `room_session_persist` | 17 | Harvest pipeline; many lazy imports |
| `room_consensus_rounds` | 13 | Consensus FSM |
| `room_turn_flow` | 13 | `run_room` / `continue_room_round` entry |
| `room_agent_invoke` | 12 | Agent call + SSE |
| `room_turn_meta` | 8 | Plan sync, scribe triggers |
| `room_plan_scribe` | 7 | Plan synthesis |
| `room_parallel_rounds` | 6 | Parallel agent rounds |
| `room_tasks` | 5 | Team task board |

## Public API surfaces

### 1. Facade — `agent_lab.room` (`room.py` `__all__`)

Primary entry for app server, scripts, and most tests:

- Turn drivers: `run_room`, `continue_room_round`, `run_agent_rounds`, `run_consensus_agent_rounds`, `run_parallel_round`
- Session I/O: `load_session_messages`, `save_room_session`, `room_session_context`
- Plan/scribe: `synthesize_plan`, `synthesize_session_plan`, `ensure_*_plan_*`, `maybe_auto_scribe_*`
- Types/constants: `ChatMessage`, `AgentId`, `PLAN_FORMAT_VERSION`, parallel round limits
- Internal names exported for tests/deps: `_session_context`, `_call_one_agent`, `_delegate_run_meta_patch`, …

All `room_*` implementation modules live under `agent_lab/room/` (28 modules). Root shims **removed** — use `agent_lab.room.*` only.

The public facade (`from agent_lab.room import run_room`) uses lazy exports in `room/__init__.py` so submodule imports (e.g. `agent_lab.room.sse_stream`) do not pull the full orchestration graph.

### 2. Direct `agent_lab.room.*` subpaths (wave 2d+)

External code imports canonical subpaths (e.g. `agent_lab.room.context`, `agent_lab.room.tasks`).
Root `room_*.py` shims **removed**.

Enforced by:

```bash
make audit-room-imports
# tests/test_structure_metrics.py::test_audit_room_legacy_imports_passes
```

## Known structural issue — facade cycle

`room_dispatch.py` lazy-imports the facade:

```python
from agent_lab.room import ChatMessage, _call_one_agent, _session_context
```

That creates `room_dispatch → room → … → room_turn_meta → room_dispatch` cycle risk, currently broken by lazy imports inside functions.

**Wave 2 prerequisite:** replace facade imports in `room_dispatch` with direct imports from `room.messages` / `room.agent_invoke` / `room.session_persist` before moving files.

Detect regressions:

```bash
python scripts/room_import_graph.py --strict   # enforced in tests/test_structure_metrics.py (wave 2a+)
```

## Migration phases

| Phase | Action | Done when |
|-------|--------|-----------|
| **1 (this PR)** | Metrics + design + import graph tooling | Docs + scripts + tests green |
| **2a** | Break `room_dispatch → room` facade imports | `--strict` passes ✅ |
| **2b** | Move leaf modules + shims | `make test-fast`, import paths unchanged ✅ |
| **2c** | Move hub/domain modules + shims | `make test-fast`, import paths unchanged ✅ |
| **2d** | Migrate external imports to `agent_lab.room.*`; audit script | `audit-room-imports` passes ✅ |
| **3** | mypy strict ratchet on `agent_lab.room.*` | `make typecheck-room-ratchet` ✅ (0/0) |
| **4** | Delete root `room_*.py` shims | `audit-room-imports` passes, no shims ✅ |

Move order suggestion: leaf → domain → policy → invoke → orchestration → delete shims.

## Plan package (parallel wave — shipped)

See [PLAN-PACKAGE-REFACTOR-DESIGN.md](PLAN-PACKAGE-REFACTOR-DESIGN.md).

| Phase | Action | Done when |
|-------|--------|-----------|
| **1** | Move `plan_*.py` → `plan/`, rewrite imports | `audit-plan-imports` ✅ |
| **2** | mypy strict ratchet on `agent_lab.plan.*` | `make typecheck-plan-ratchet` ✅ (0/0) |

## Verification gates

Each wave:

```bash
make structure-metrics-check
make audit-room-imports
make audit-plan-imports
make typecheck-room-ratchet
make typecheck-plan-ratchet
make test-fast
python scripts/room_import_graph.py --strict
python scripts/audit_runtime_imports.py
```

Manual: room SSE turn + plan scribe smoke (`make smoke` or `scripts/smoke_room.py`).

## Out of scope (later waves)

- `session_*`, `kimi_*` subpackages
- Makefile domain split
- `RoomChat.tsx` component extraction

## Reference

- Runtime precedent: `src/agent_lab/runtime/__init__.py` curated `__all__`
- Cross-lane contract: `src/agent_lab/runtime/import_graph.py`
- Structure baseline: [STRUCTURE-METRICS.md](STRUCTURE-METRICS.md)
