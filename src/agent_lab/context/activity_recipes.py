"""CX2 (docs/redesign-2026-07/09-context-engineering.md §11) — per-activity
ContextNeed recipes.

First draft translating §6's prose specs (필수/선택/제외 per activity) into
typed ``ContextNeed`` instances over ``SourceClass``. CX2's own acceptance
criteria requires Human review before these are load-bearing — token budgets
in particular are provisional estimates, not measured. Treat this module as
the reviewable artifact, not a finished contract.

Each recipe's docstring quotes the §6 subsection it translates so a reviewer
can check the mapping without re-deriving it.
"""

from __future__ import annotations

from agent_lab.context.recipe import ActivityKind, ContextNeed, SourceClass

CLARIFY_RECIPE = ContextNeed(
    activity=ActivityKind.CLARIFY,
    # §6.1 필수: Human topic, workspace identity, unresolved requirements, prior answers.
    # 2026-07-16 review: SYSTEM_INVARIANT was missing — every activity operates
    # inside the same always-on Human gate/security/worktree boundaries, clarify
    # included, even though §6.1's prose doesn't call it out explicitly.
    required_sources=frozenset(
        {
            SourceClass.SYSTEM_INVARIANT,
            SourceClass.HUMAN_INTENT,
            SourceClass.PROJECT_DOC,
            SourceClass.RUNTIME_STATE,
        }
    ),
    optional_sources=frozenset(),
    # §6.1 제외: 전체 repo dump, execute trace, 장기 wisdom 대부분.
    forbidden_sources=frozenset(
        {SourceClass.REPO_CONTEXT, SourceClass.EVIDENCE, SourceClass.SEMANTIC_MEMORY, SourceClass.EPISODE}
    ),
    token_budget=4_000,
)

PLAN_RECIPE = ContextNeed(
    activity=ActivityKind.PLAN,
    # §6.2 필수: goal, constraints, repo map, 관련 파일/API, shipped traceability, prior decisions.
    required_sources=frozenset(
        {
            SourceClass.HUMAN_INTENT,
            SourceClass.SYSTEM_INVARIANT,
            SourceClass.REPO_CONTEXT,
            SourceClass.PROJECT_DOC,
            SourceClass.RUNTIME_STATE,
        }
    ),
    # §6.2 선택: 유사 episode, 외부 docs, 다른 agent 제안/분석 — Room이 멀티에이전트라
    # plan specialist가 동료 제안을 참고할 수 있어야 함(2026-07-16 §6.2 프로즈에 반영,
    # AGENT_OPINION을 코드에만 넣고 문서를 안 고쳐서 생긴 drift를 닫음).
    optional_sources=frozenset({SourceClass.EPISODE, SourceClass.EXTERNAL_CONTENT, SourceClass.AGENT_OPINION}),
    forbidden_sources=frozenset(),
    # 2026-07-16 review: repo map + 관련 파일/API가 이 recipe에서 가장 큰 항목(§7.1
    # "relevant repo/docs"가 40%로 최대 배분)인데 12000은 그 몫이 좁다 — 16000으로 상향.
    # 여전히 추정치이고, select_context()는 required item이 예산을 넘으면 조용히 잘라내지
    # 않고 ContextSelectionError로 실패한다 — 예산이 너무 작으면 품질 저하가 아니라
    # 에러로 드러난다.
    token_budget=16_000,
)

CRITIC_RECIPE = ContextNeed(
    activity=ActivityKind.CRITIC,
    # §6.3 필수: 독립 rubric, plan/acceptance criteria, candidate artifact/evidence.
    required_sources=frozenset({SourceClass.SYSTEM_INVARIANT, SourceClass.APPROVED_PLAN, SourceClass.EVIDENCE}),
    optional_sources=frozenset(),
    # §6.3 제외: actor의 자기평가를 authority로 취급하지 않음 — producing agent's own
    # opinion must not reach the critic as evidence.
    forbidden_sources=frozenset({SourceClass.AGENT_OPINION}),
    token_budget=6_000,
)

EXECUTE_RECIPE = ContextNeed(
    activity=ActivityKind.EXECUTE,
    # §6.4 필수: 승인된 plan revision/hash, 해당 action, workspace/worktree, must-not,
    # verification, relevant code slice, tool grants.
    required_sources=frozenset(
        {
            SourceClass.APPROVED_PLAN,
            SourceClass.SYSTEM_INVARIANT,
            SourceClass.RUNTIME_STATE,
            SourceClass.REPO_CONTEXT,
        }
    ),
    optional_sources=frozenset(),
    # §6.4 제외: 승인 전 draft, 무관한 transcript, 다른 action의 전체 context.
    forbidden_sources=frozenset({SourceClass.EPISODE, SourceClass.EXTERNAL_CONTENT}),
    token_budget=8_000,
)

REPAIR_RECIPE = ContextNeed(
    activity=ActivityKind.REPAIR,
    # §6.5 필수: 원 plan, diff, failure evidence, prior attempts, 변경해야 할 전략.
    # 2026-07-16 review: SYSTEM_INVARIANT was missing — repair re-enters the same
    # tool-grant/must-not boundaries EXECUTE_RECIPE requires; it's a retry of
    # execute, not a lighter-weight activity.
    required_sources=frozenset(
        {
            SourceClass.SYSTEM_INVARIANT,
            SourceClass.APPROVED_PLAN,
            SourceClass.EVIDENCE,
            SourceClass.RUNTIME_STATE,
        }
    ),
    # §6.5 전략 후보 — 승인된 패턴이 있다면.
    optional_sources=frozenset({SourceClass.SEMANTIC_MEMORY, SourceClass.HUMAN_INTENT}),
    # §6.5 제외: 실패한 동일 prompt의 무가공 반복 — source class로 강제할 수 없는 절차적
    # 규칙이라 여기서는 무관한 외부 콘텐츠만 배제.
    forbidden_sources=frozenset({SourceClass.EXTERNAL_CONTENT}),
    # 2026-07-16 review: repair accumulates prior attempts across repeated cycles
    # (bounded by max_repair_attempts=2 elsewhere) — 8000 risks the required-item
    # budget error tripping as history grows. 10000 gives more headroom.
    token_budget=10_000,
)

SCRIBE_RECIPE = ContextNeed(
    activity=ActivityKind.SCRIBE,
    # §6.6 필수: 합의된 결정, objection 상태, source refs, plan contract template.
    required_sources=frozenset({SourceClass.RUNTIME_STATE, SourceClass.EVIDENCE, SourceClass.SYSTEM_INVARIANT}),
    optional_sources=frozenset(),
    # §6.6 선택: 발언 전체가 아니라 structured contributions — full episode transcript excluded.
    forbidden_sources=frozenset({SourceClass.EPISODE}),
    token_budget=6_000,
)

ACTIVITY_RECIPES: dict[ActivityKind, ContextNeed] = {
    ActivityKind.CLARIFY: CLARIFY_RECIPE,
    ActivityKind.PLAN: PLAN_RECIPE,
    ActivityKind.CRITIC: CRITIC_RECIPE,
    ActivityKind.EXECUTE: EXECUTE_RECIPE,
    ActivityKind.REPAIR: REPAIR_RECIPE,
    ActivityKind.SCRIBE: SCRIBE_RECIPE,
}


def recipe_for(activity: ActivityKind) -> ContextNeed:
    return ACTIVITY_RECIPES[activity]
