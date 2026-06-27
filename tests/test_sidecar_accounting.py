"""Sidecar cost ledger + trace accounting."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.sidecar_accounting import (
    persist_sidecar_ledger,
    sidecar_bridge_handler,
    tracked_agent_call,
)
from agent_lab.run_meta import read_run_meta

def test_sidecar_bridge_records_usage(tmp_path: Path) -> None:
    folder = tmp_path / "sess-1"
    folder.mkdir()
    (folder / "run.json").write_text("{}\n", encoding="utf-8")

    bridge, run_meta = sidecar_bridge_handler(folder, "claude", kind="oracle")
    bridge(
        "usage",
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_cost_usd": 0.01,
        },
    )
    persist_sidecar_ledger(folder, run_meta)
    run = read_run_meta(folder)
    claude = (run.get("cost_ledger") or {}).get("by_agent", {}).get("claude", {})
    assert claude.get("calls") == 1
    assert claude.get("tokens_in") == 100


def test_tracked_agent_call_writes_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "sess-2"
    folder.mkdir()
    (folder / "run.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_TRACE", "1")

    out = tracked_agent_call(
        folder,
        "claude",
        kind="scribe",
        fn=lambda bridge: (bridge("usage", {"input_tokens": 5, "output_tokens": 2}), "ok")[1],
    )
    assert out == "ok"
    trace_path = folder / "trace.jsonl"
    assert trace_path.is_file()
    lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    import json

    span = json.loads(lines[-1])
    assert span.get("kind") == "agent"
    assert span.get("name") == "scribe:claude"
