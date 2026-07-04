from __future__ import annotations

"""Plan workflow peer review round."""

from pathlib import Path
from typing import Any

PLAN_PEER_REVIEW_GUIDANCE = (
    "Plan peer review: read plan.md only. Do not propose code changes. "
    "Use envelope CHALLENGE or ENDORSE on specific plan actions or sections. "
    "Reference plan_action:N in refs when applicable."
)

PLAN_ARCHITECT_REVIEW_GUIDANCE = (
    "Plan architect review (ralplan architect seat): read plan.md only. "
    "Evaluate structure, dependencies, scope boundaries, and whether each action has "
    "a testable verify criterion. CHALLENGE architectural gaps; ENDORSE when the plan "
    "is coherent. No code changes."
)

PLAN_CRITIC_REVIEW_GUIDANCE = (
    "Plan critic review (ralplan critic seat): adversarial read of plan.md only. "
    "Find the weakest assumption, missing edge case, or unverifiable claim. "
    "CHALLENGE or AMEND one concrete issue; ENDORSE only with a one-line rationale. "
    "No code changes."
)


PLAN_FRESH_EYES_GUIDANCE = (
    "[anti-drift · fresh-eyes 냉정 검토] 이전 토론 맥락 없이 plan.md만 처음 보는 외부 검토자로서 "
    "읽으세요. 합의가 형성됐다는 가정을 버리고, 가장 위험한 가정·누락된 엣지케이스·검증 불가한 "
    "주장 1건을 골라 CHALLENGE 또는 AMEND envelope로 제시하세요. 정말 문제가 없으면 근거를 한 줄로 "
    "밝히고 ENDORSE 하세요. 코드 변경은 제안하지 마세요."
)
def run_plan_peer_review_round(
    folder: Path,
    *,
    topic: str,
    messages: list[Any],
    agents: list[str] | None,
    permissions: dict[str, Any] | None,
    run_meta: dict[str, Any] | None,
    plan_md: str,
    on_event: Any | None = None,
) -> list[Any]:
    """Read-only peer review of plan.md by non-scribe agents."""
    from agent_lab.agents.registry import AGENT_IDS, available_agents
    from agent_lab.plan.peer_seats import (
        plan_cold_critic_enabled,
        plan_peer_review_seats,
        plan_peer_review_uses_role_lanes,
        plan_scribe_agent,
    )
    from agent_lab.room import run_parallel_round

    active = [a for a in (agents or available_agents()) if a in AGENT_IDS]
    active_ids = [str(a) for a in active]
    scribe_raw = plan_scribe_agent(run_meta=run_meta, active=active_ids)
    reviewers = plan_peer_review_seats(active_ids, run_meta=run_meta)
    if not reviewers:
        return []

    if run_meta is not None:
        from agent_lab.run.meta import stamp_run_meta

        stamp_run_meta(
            run_meta,
            _plan_peer_review=True,
            _plan_scribe_agent=scribe_raw,
        )

    replies: list[Any] = []
    if plan_peer_review_uses_role_lanes(run_meta=run_meta) and len(reviewers) >= 2:
        architect, critic = reviewers[0], reviewers[1]
        replies.extend(
            run_parallel_round(
                topic,
                messages,
                agents=[architect],  # type: ignore[arg-type]
                parallel_round=1,
                on_event=on_event,
                permissions=permissions,
                plan_md=plan_md,
                run_meta=run_meta,
                extra_follow_up=PLAN_ARCHITECT_REVIEW_GUIDANCE,
                task_type="peer_review",
            )
        )
        replies.extend(
            run_parallel_round(
                topic,
                messages + replies,
                agents=[critic],  # type: ignore[arg-type]
                parallel_round=1,
                on_event=on_event,
                permissions=permissions,
                plan_md=plan_md,
                run_meta=run_meta,
                extra_follow_up=PLAN_CRITIC_REVIEW_GUIDANCE,
                task_type="peer_review",
            )
        )
    else:
        replies.extend(
            run_parallel_round(
                topic,
                messages,
                agents=reviewers,  # type: ignore[arg-type]
                parallel_round=1,
                on_event=on_event,
                permissions=permissions,
                plan_md=plan_md,
                run_meta=run_meta,
                extra_follow_up=PLAN_PEER_REVIEW_GUIDANCE,
                task_type="peer_review",
            )
        )

    if plan_cold_critic_enabled(run_meta=run_meta) and reviewers:
        cold_critic = reviewers[-1]
        replies.extend(
            run_parallel_round(
                topic,
                [],
                agents=[cold_critic],  # type: ignore[arg-type]
                parallel_round=1,
                on_event=on_event,
                permissions=permissions,
                plan_md=plan_md,
                run_meta=run_meta,
                extra_follow_up=PLAN_FRESH_EYES_GUIDANCE,
                task_type="cold_critic",
            )
        )

    from agent_lab.plan.peer_iterate import finalize_plan_peer_review_round

    human_turn = int((run_meta or {}).get("human_turn") or 0)
    finalize_plan_peer_review_round(
        folder,
        run_meta=run_meta,
        replies=replies,
        human_turn=human_turn,
    )

    return replies
