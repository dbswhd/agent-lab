"""Consensus agreement tracking for plan sync prompts."""

from __future__ import annotations

from agent_lab.consensus_agreements import (
    agreement_plan_synced_notice,
    agreement_sync_failed_notice,
    mark_agreements_plan_synced,
    pending_consensus_agreements,
    record_consensus_agreement,
    short_excerpt,
)
from agent_lab.room_context import plan_stale_banner


def test_record_and_sync_consensus_agreement():
    consensus = {
        "status": "reached",
        "anchor": {"excerpt": "build.mjs dry-run 감audit 추가", "agent": "cursor"},
    }
    rows = record_consensus_agreement(
        [],
        consensus=consensus,
        message_count=12,
        ts="2026-05-31T00:00:00+00:00",
    )
    assert len(rows) == 1
    assert rows[0]["plan_synced"] is False
    assert "dry-run" in rows[0]["excerpt"]

    synced = mark_agreements_plan_synced(
        rows,
        message_count=12,
        synced_at="2026-05-31T00:01:00+00:00",
    )
    assert synced[0]["plan_synced"] is True
    assert pending_consensus_agreements(synced) == []


def test_plan_stale_banner_uses_consensus_topic():
    run = {
        "consensus_agreements": [
            {
                "excerpt": "절 경계 fill% dry-run",
                "status": "reached",
                "plan_synced": False,
            }
        ]
    }
    banner = plan_stale_banner(run)
    assert banner == agreement_sync_failed_notice(
        "절 경계 fill% dry-run",
        "plan.md 자동 정리 후 수동 확인 필요",
    )


def test_notice_labels():
    excerpt = "Puppeteer 후처리로 theme fill% 측정"
    topic = short_excerpt(excerpt)
    synced = agreement_plan_synced_notice(excerpt, "합의된 점, 지금 실행 반영")
    assert topic in synced
    assert "plan.md 반영" in synced
    assert "합의된 점" in synced
    assert "자동 정리 실패" in agreement_sync_failed_notice(excerpt, "err")
