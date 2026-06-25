"""Room preset catalog — topic_router + role orchestration 프리셋 조합."""

from __future__ import annotations

from typing import Any


def preset_catalog() -> list[dict[str, Any]]:
    """사용 가능한 Room 프리셋 목록. role_policy: auto|force|off."""
    return [
        {
            "id": "consensus",
            "label": "합의 토론",
            "description": "기본 3-agent 합의 루프. 카테고리·역할은 topic_router가 자동 결정.",
            "role_policy": "auto",
            "category_hint": None,
        },
        {
            "id": "producer_reviewer",
            "label": "Producer → Reviewer",
            "description": (
                "Producer 제안 → Reviewer 검증 → 재조합 합성 → Oracle 검증. "
                "cursor=proposer, claude=critic, codex=executor로 역할 고정."
            ),
            "role_policy": "force",
            "category_hint": "standard",
            "forced_roles": {"cursor": "proposer", "claude": "critic", "codex": "executor"},
        },
        {
            "id": "quick",
            "label": "빠른 단답",
            "description": "단일 에이전트 단답. 역할 배정 없음.",
            "role_policy": "off",
            "category_hint": "quick",
        },
        {
            "id": "pipeline",
            "label": "파이프라인",
            "description": "순차 단계 실행. 역할은 topic_router 자동 결정.",
            "role_policy": "auto",
            "category_hint": None,
        },
        {
            "id": "supervisor",
            "label": "Supervisor",
            "description": "Supervisor 에이전트가 서브태스크를 배분. 역할 배정 없음.",
            "role_policy": "off",
            "category_hint": None,
        },
    ]
