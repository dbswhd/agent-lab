"""Cost ledger + trace spans for agent calls outside the Room SSE agent round path."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from agent_lab.cost_ledger import record_agent_usage, usage_from_bridge
from agent_lab.run_meta import patch_run_meta, read_run_meta
from agent_lab.trace_recorder import record_agent_span

T = TypeVar("T")
BridgeFn = Callable[[str, dict[str, Any]], None]


def _human_turn_from_run(run_meta: dict[str, Any] | None) -> int | None:
    if not isinstance(run_meta, dict):
        return None
    turns = run_meta.get("turns")
    if isinstance(turns, list) and turns:
        return max(0, len(turns) - 1)
    return None


def sidecar_bridge_handler(
    folder: Path,
    agent_id: str,
    *,
    kind: str,
    human_turn: int | None = None,
) -> tuple[BridgeFn, dict[str, Any]]:
    """Build an ``on_bridge_event`` handler that accumulates into in-memory run_meta."""
    run_meta = read_run_meta(folder)
    turn = human_turn if human_turn is not None else _human_turn_from_run(run_meta)

    def on_bridge(event_kind: str, data: dict[str, Any]) -> None:
        if event_kind != "usage":
            return
        usage = usage_from_bridge(data)
        if usage is not None:
            record_agent_usage(run_meta, agent_id, usage, turn=turn)

    return on_bridge, run_meta


def persist_sidecar_ledger(folder: Path, run_meta: dict[str, Any]) -> None:
    ledger = run_meta.get("cost_ledger")
    if not isinstance(ledger, dict):
        return

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        run["cost_ledger"] = ledger
        return run

    patch_run_meta(folder, _patch)


def flush_sidecar_call(
    folder: Path,
    run_meta: dict[str, Any],
    *,
    kind: str,
    agent_id: str,
    started_at: float,
    status: str = "ok",
) -> None:
    dur_ms = round((time.monotonic() - started_at) * 1000.0, 1)
    persist_sidecar_ledger(folder, run_meta)
    ledger = run_meta.get("cost_ledger") if isinstance(run_meta.get("cost_ledger"), dict) else {}
    by_agent = ledger.get("by_agent") if isinstance(ledger.get("by_agent"), dict) else {}
    entry = by_agent.get(agent_id) if isinstance(by_agent.get(agent_id), dict) else {}
    record_agent_span(
        folder,
        name=f"{kind}:{agent_id}",
        agent_id=agent_id,
        dur_ms=dur_ms,
        status=status,
        tokens_in=int(entry.get("tokens_in", 0) or 0),
        tokens_out=int(entry.get("tokens_out", 0) or 0),
        usd=float(entry.get("usd", 0.0) or 0.0),
        data={"kind": kind},
    )


def tracked_agent_call(
    folder: Path,
    agent_id: str,
    *,
    kind: str,
    fn: Callable[[BridgeFn | None], T],
    human_turn: int | None = None,
) -> T:
    """Run ``fn(on_bridge_event)`` with cost ledger + trace accounting."""
    bridge, run_meta = sidecar_bridge_handler(
        folder,
        agent_id,
        kind=kind,
        human_turn=human_turn,
    )
    started = time.monotonic()
    status = "ok"
    try:
        return fn(bridge)
    except Exception:
        status = "error"
        raise
    finally:
        flush_sidecar_call(
            folder,
            run_meta,
            kind=kind,
            agent_id=agent_id,
            started_at=started,
            status=status,
        )
