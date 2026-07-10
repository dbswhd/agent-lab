from __future__ import annotations

from agent_lab.time_utils import utc_now_iso


def test_utc_now_iso_ends_with_offset_or_z() -> None:
    value = utc_now_iso()
    assert "T" in value
    assert value.endswith("+00:00") or value.endswith("Z")
