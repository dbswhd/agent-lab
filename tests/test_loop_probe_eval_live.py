from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live


def test_live_loop_model_eval_cursor() -> None:
    if os.getenv("AGENT_LAB_RUN_LIVE") != "1":
        pytest.skip("Set AGENT_LAB_RUN_LIVE=1 for live loop eval")

    from agent_lab.loop_probe_eval import eval_loop_profile_row

    row = eval_loop_profile_row("cursor", static_only=False)
    assert row is not None
    assert row["eval_source"] == "live"
    assert row["supports_tools"] is True
