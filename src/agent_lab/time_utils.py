from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Current aware UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """UTC ISO-8601 timestamp for run.json and ledger serialization."""
    return utc_now().isoformat()


def utc_now_iso_seconds() -> str:
    """UTC ISO-8601 without fractional seconds."""
    return utc_now().replace(microsecond=0).isoformat()


def utc_now_iso_z() -> str:
    """UTC ISO-8601 with Z suffix and no fractional seconds."""
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
