"""ABSORB P1-monitor — CI/log watch events → evidence ledger (read-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_lab.evidence_ledger import append_evidence
from agent_lab.run.meta import patch_run_meta, read_run_meta

_MAX_DETAIL = 2000
_ALLOWED_KINDS = frozenset(
    {"ci_status", "log_tail", "merge_checks", "hook", "external", "manual"}
)


def record_monitor_event(
    folder: Path,
    *,
    kind: str,
    detail: str = "",
    refs: list[str] | None = None,
    ok: bool | None = None,
) -> dict[str, Any]:
    """Append a MONITOR-phase evidence row. Does not approve or execute."""
    cleaned_kind = (kind or "manual").strip().lower() or "manual"
    if cleaned_kind not in _ALLOWED_KINDS:
        cleaned_kind = "manual"
    text = (detail or "").strip()
    if len(text) > _MAX_DETAIL:
        text = text[:_MAX_DETAIL].rstrip() + "…"
    event: dict[str, Any] = {
        "phase": "MONITOR",
        "kind": cleaned_kind,
        "detail": text or cleaned_kind,
    }
    if refs:
        event["refs"] = [str(r).strip() for r in refs if str(r).strip()][:20]
    if ok is not None:
        event["ok"] = bool(ok)
    return append_evidence(folder, event)


def maybe_record_merge_checks_monitor(
    folder: Path,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """When merge checks fail, append one MONITOR row (fingerprint-deduped)."""
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return None
    failing = [
        c
        for c in checks
        if isinstance(c, dict) and c.get("ok") is False
    ]
    if not failing:
        return None
    fingerprint = "|".join(
        f"{c.get('id')}:{c.get('detail')}" for c in failing
    )
    run = read_run_meta(folder)
    if str(run.get("monitor_merge_checks_fp") or "") == fingerprint:
        return None

    detail = "; ".join(
        f"{c.get('id')}={c.get('detail') or 'fail'}" for c in failing[:8]
    )
    row = record_monitor_event(
        folder,
        kind="merge_checks",
        detail=detail,
        refs=[str(c.get("id")) for c in failing if c.get("id")],
        ok=False,
    )

    def _patch(meta: dict[str, Any]) -> dict[str, Any]:
        meta["monitor_merge_checks_fp"] = fingerprint
        return meta

    patch_run_meta(folder, _patch)
    return row
