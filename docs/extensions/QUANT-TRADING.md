# Quant trading extension (optional)

Agent-lab **core** (Room, sessions, agents, FastAPI UI) runs standalone. Quant integration is an **optional extension** that wires sibling repos when present.

**Logic SSoT:** `quant-agentic-trading` owns `card_builder`, `confidence`, and `market_read`. Agent-lab Trading Mission modules delegate via `extensions/quant_runtime.py`.

## Sibling repos

| Repo | Role | Env |
|------|------|-----|
| [pipeline](https://github.com/dbswhd/pipeline) | KR research, freshness, card/playbook **data host** | `QUANT_PIPELINE_ROOT` |
| [quant-agentic-trading](https://github.com/dbswhd/quant-agentic-trading) | Control plane ingest, risk, quant-trading MCP | `AGENTIC_QUANT_PIPELINE_SRC`, `AGENTIC_TRADING_DB` |

Code lives under `src/agent_lab/extensions/quant_trading.py`. Trading Mission modules (`trading_mission/`, `pipeline_market_read.py`, research MCP market tools) call this layer and return structured `extension` errors when a repo is missing.

## Core vs extension

| Core (no sibling repos) | Extension (requires siblings) |
|-------------------------|-------------------------------|
| `make install`, `make api`, Room runs | `make artifact-cards`, `make offline-lane` |
| Workspace preset `agent-lab` | Workspace preset `quant-pipeline` |
| Templates: general, book-* | Templates: trading-mission, trading-thin, trading-offline |
| Mock quote (`AGENT_LAB_QUOTE_MODE=mock`) without pipeline | Freshness, overlay signals, card sync |
| Session playbook from `artifacts/` only | Pipeline `data/agentic/playbook.md` fallback |

Trading templates and the `quant-pipeline` workspace preset are **hidden** until `QUANT_PIPELINE_ROOT` resolves to an existing directory.

## Typical env (extension)

```bash
export QUANT_PIPELINE_ROOT=~/Desktop/pipeline
export AGENTIC_QUANT_PIPELINE_SRC=~/Projects/quant-agentic-trading/src
export AGENTIC_TRADING_DB=~/Projects/quant-agentic-trading/data/agentic_trading/control_plane.sqlite3
export AGENT_LAB_FRESHNESS_PYTHON=$QUANT_PIPELINE_ROOT/.venv/bin/python
```

Optional `~/.agent-lab/config.toml` paths (commented by default on first run):

```toml
[paths]
# quant_pipeline = "/path/to/pipeline"
# agentic_trading = "/path/to/quant-agentic-trading"
```

## Make targets (extension only)

Run from **agent-lab** repo root:

- `make verify-mcp-contract`
- `make artifact-cards` / `make offline-lane`
- `make verify-trading-v1`

See also `docs/MCP-TOOL-CONTRACT.md`, `docs/trading-mission/`.
