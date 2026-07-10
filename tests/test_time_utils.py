from __future__ import annotations

from agent_lab.time_utils import utc_now, utc_now_iso, utc_now_iso_seconds, utc_now_iso_z


def test_utc_now_is_aware_utc() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() is not None


def test_utc_now_iso_ends_with_offset_or_z() -> None:
    value = utc_now_iso()
    assert "T" in value
    assert value.endswith("+00:00") or value.endswith("Z")


def test_utc_now_iso_seconds_has_no_fraction() -> None:
    value = utc_now_iso_seconds()
    assert "T" in value
    assert "." not in value.split("T", 1)[1]


def test_utc_now_iso_z_uses_z_suffix() -> None:
    value = utc_now_iso_z()
    assert value.endswith("Z")
    assert "." not in value.split("T", 1)[1]
