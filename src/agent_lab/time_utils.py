from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """UTC ISO-8601 timestamp for run.json and ledger serialization."""
    return datetime.now(timezone.utc).isoformat()
