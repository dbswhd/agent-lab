"""Emergence KPI — dispatch_fanout_rate (CMD-RDP)."""

from __future__ import annotations

from agent_lab.emergence_kpis import dispatch_fanout_rate


def test_dispatch_fanout_rate_from_ledger():
    rate, counts = dispatch_fanout_rate(
        {
            "dispatch_ledger": [
                {"op": "parallel_delegate", "status": "done"},
                {"op": "single_delegate", "status": "done"},
            ]
        }
    )
    assert rate == 0.5
    assert counts["parallel"] == 1
    assert counts["single"] == 1
