# F5 — Trading isolation decision (2026-07)

> Status: **decided** · NORTH-STAR F5 · trading delta **0** on core PRs

## Decision

`src/agent_lab/trading_mission/` and `src/agent_lab/quant/` remain **extension-lane subpackages** in-tree. They are **not** part of Mission OS core (Room · plan · inbox · autonomy).

Physical move to `examples/` or a separate repo is **deferred** (high import/test surface). Isolation is enforced by policy + review, not a big-bang move.

## Boundaries

| Layer | Path | Rule |
|-------|------|------|
| Core | `room/`, `plan/`, `inbox/`, `run/`, `session/`, `mission/` (non-trading) | No new trading imports |
| Extension facade | `extensions/quant_trading.py`, `extensions/quant_runtime.py` | Only core→trading entry |
| Extension lane | `trading_mission/`, `quant/`, `pipeline_*_read.py` | Trading-only changes |

## Operator config

Optional paths stay in `~/.agent-lab/config.toml` (`paths.quant_pipeline`, `paths.agentic_trading`) — commented by default in `app_config.default_config_dict()`.

## Acceptance

- Core PRs (Room, plan, autonomy, cleanup): **trading delta 0**
- Trading work: dedicated PR labeled extension-lane
- Docs: this file + NORTH-STAR §3.1 / §3.3

## Non-goals (this decision)

- Moving packages on disk
- Deleting trading tests
- Changing live trading behavior
