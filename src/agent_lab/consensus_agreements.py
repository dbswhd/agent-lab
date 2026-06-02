"""Track consensus topics awaiting or completed plan sync."""

from __future__ import annotations

import uuid
from typing import Any


def short_excerpt(text: str, *, max_len: int = 52) -> str:
    body = " ".join((text or "").split())
    if not body:
        return "합의 사항"
    if len(body) <= max_len:
        return body
    return body[: max_len - 1].rstrip() + "…"


def agreement_topic_label(excerpt: str) -> str:
    return short_excerpt(excerpt)


def agreement_plan_synced_notice(excerpt: str, summary: str = "") -> str:
    topic = agreement_topic_label(excerpt)
    detail = f": {summary.strip()}" if summary.strip() else ""
    return f"[{topic}] 합의 완료 · plan.md 반영{detail}"


def agreement_sync_failed_notice(excerpt: str, message: str = "") -> str:
    topic = agreement_topic_label(excerpt)
    detail = f" ({message.strip()})" if message.strip() else ""
    return f"[{topic}] plan.md 자동 정리 실패{detail}"


def agreement_reached_notice(excerpt: str) -> str:
    return f"[{agreement_topic_label(excerpt)}] 사항 합의 완료 → plan.md 정리 중"


def agreement_synced_notice(excerpt: str) -> str:
    return agreement_plan_synced_notice(excerpt)


def agreement_pending_notice(excerpt: str) -> str:
    return f"[{agreement_topic_label(excerpt)}] 사항 합의 완료 → plan 정리 필요"


def consensus_topic_excerpt(consensus: dict[str, Any] | None) -> str:
    return _anchor_excerpt(consensus)


def _anchor_excerpt(consensus: dict[str, Any] | None) -> str:
    if not consensus:
        return ""
    anchor = consensus.get("anchor") or {}
    if isinstance(anchor, dict):
        return str(anchor.get("excerpt") or "").strip()
    return ""


def record_consensus_agreement(
    prev_agreements: list[dict[str, Any]] | None,
    *,
    consensus: dict[str, Any] | None,
    message_count: int,
    ts: str,
) -> list[dict[str, Any]]:
    """Append a reached consensus topic if not duplicate of the latest pending row."""
    if not consensus or consensus.get("status") != "reached":
        return list(prev_agreements or [])

    excerpt = _anchor_excerpt(consensus)
    if not excerpt:
        return list(prev_agreements or [])

    agreements = list(prev_agreements or [])
    if agreements:
        last = agreements[-1]
        if (
            not last.get("plan_synced")
            and last.get("excerpt") == excerpt
            and last.get("message_count") == message_count
        ):
            return agreements

    agreements.append(
        {
            "id": f"agr-{uuid.uuid4().hex[:8]}",
            "excerpt": excerpt,
            "status": "reached",
            "message_count": message_count,
            "ts": ts,
            "plan_synced": False,
        }
    )
    return agreements


def mark_agreements_plan_synced(
    agreements: list[dict[str, Any]] | None,
    *,
    message_count: int,
    synced_at: str,
) -> list[dict[str, Any]]:
    rows = list(agreements or [])
    for row in rows:
        if row.get("plan_synced"):
            continue
        if int(row.get("message_count") or 0) <= message_count:
            row["plan_synced"] = True
            row["plan_synced_at"] = synced_at
    return rows


def pending_consensus_agreements(
    agreements: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return [row for row in (agreements or []) if not row.get("plan_synced")]
