"""Human Inbox follow-up questions from token/context optimization Room session."""

from __future__ import annotations

from typing import Any

TOKEN_OPT_DEFERRED_INBOX_ID = "inbox-b0c54dcc3db1"

TOKEN_OPT_FOLLOWUP_QUESTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "token-opt-p1-follow-budget",
        "prompt": "combined_follow(lead/hook/plan clarify)를 예산 meta에 포함 — GO?",
        "options": [
            {"id": "go", "label": "GO", "description": "agent_invoke + token_budget 정확도", "recommended": True},
            {"id": "defer", "label": "보류", "description": "추가 측정 후"},
        ],
    },
    {
        "id": "token-opt-p1-compact-tool",
        "prompt": "Tool output 압축 기본 ON + char trim 전 적용 — GO?",
        "options": [
            {"id": "go", "label": "GO", "description": "COMPACT_TOOL_OUTPUT default on", "recommended": True},
            {"id": "defer", "label": "보류", "description": "opt-in 유지"},
        ],
    },
    {
        "id": "token-opt-p1-token-est",
        "prompt": "Loop token cap 추정을 cost_ledger.chars_to_tokens SSOT로 통일 — GO?",
        "options": [
            {"id": "go", "label": "GO", "description": "turn_modes + ledger 일치", "recommended": True},
            {"id": "defer", "label": "보류", "description": "chars//4 유지"},
        ],
    },
    {
        "id": "token-opt-p2-adaptive",
        "prompt": "adaptive_efficiency 선제 트리거(human_turn≥5 · context critical) — GO?",
        "options": [
            {"id": "go", "label": "GO", "description": "예방적 컨텍스트 축소", "recommended": True},
            {"id": "defer", "label": "보류", "description": "over(100%)만 유지"},
        ],
    },
    {
        "id": "token-opt-harness-eval",
        "prompt": "eval_harness pytest XML adapter 먼저 vs Docker sandbox PoC?",
        "options": [
            {
                "id": "pytest_adapter",
                "label": "pytest adapter 먼저",
                "description": "Claude 합의 — corpus + score_instance",
                "recommended": True,
            },
            {"id": "docker_poc", "label": "Docker PoC 먼저", "description": "격리 선행"},
        ],
    },
)


def resolve_deferred_token_opt_inbox(human_inbox: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark session deferred constraint question resolved when follow-ups are materialized."""
    out: list[dict[str, Any]] = []
    for item in human_inbox:
        row = dict(item)
        if row.get("id") == TOKEN_OPT_DEFERRED_INBOX_ID and row.get("status") == "deferred":
            row["status"] = "resolved"
            row["resolution"] = "token_opt_followup_materialized"
        out.append(row)
    return out
