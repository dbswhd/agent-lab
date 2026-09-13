"""Idea-lane output contract, narration cleanup, and repository-claim boundary."""

from __future__ import annotations

from agent_lab.divergence import parse_idea_option
from agent_lab.room.context.ideation_quality import (
    IDEATION_OUTPUT_CONTRACT,
    ideation_synthesis_block,
    option_is_synthesis_ready,
    sanitize_ideation_text,
    unverified_repo_claims,
)


def test_sanitize_removes_process_narration_but_keeps_candidate_content() -> None:
    cleaned, removed = sanitize_ideation_text(
        "레포를 먼저 확인하겠습니다.\n## 제목: 학업 인박스\n핵심 원리: 마감과 출석을 한곳에 모은다.\n"
    )

    assert "레포를 먼저" not in cleaned
    assert "학업 인박스" in cleaned
    assert removed == ["레포를 먼저 확인하겠습니다."]


def test_unverified_repository_claim_is_classified_until_evidence_exists() -> None:
    claims = unverified_repo_claims("레포에 이미 백테스트 엔진이 구현되어 있다.")
    assert claims == ["레포에 이미 백테스트 엔진이 구현되어 있다."]
    assert unverified_repo_claims("레포에 백테스트 엔진이 있다 (ref: src/backtest.py#L10)") == []
    assert unverified_repo_claims("레포에 백테스트 엔진이 있다 (ref: 확인 필요)")


def test_parsed_option_keeps_raw_reply_and_marks_quality_contract() -> None:
    option = parse_idea_option(
        "도구를 먼저 호출해 파일을 확인하겠습니다.\n"
        "- **제목:** 근거형 노트\n"
        "- **핵심 원리:** 원문 위치를 보존한다.\n"
        "- **사용 장면:** 시험 전 복습\n"
        "- **차이:** 요약과 다르다.\n"
        "- **tradeoff:** 검토 시간이 든다.\n"
        "- **첫 실험:** PDF 한 개로 비교한다.\n",
        option_id="opt-0-codex",
        agent="codex",
    )

    assert "도구를 먼저" in option["raw"]
    assert "도구를 먼저" not in option["principle"]
    assert option["quality"]["contract"] == IDEATION_OUTPUT_CONTRACT
    assert option["quality"]["status"] == "ready"
    assert option["quality"]["meta_lines_removed"] == 1
    assert option_is_synthesis_ready(option)


def test_prompt_labels_parse_as_ready_contract() -> None:
    option = parse_idea_option(
        "제목: 학업 인박스\n"
        "핵심 작동 원리: 마감과 출석을 한곳에 모은다.\n"
        "실제 사용 장면 하나: 수업 전 확인한다.\n"
        "다른 접근과 무엇이 다른지: 알림만 보내지 않고 우선순위를 만든다.\n"
        "포기하는 것(tradeoff): 초기 설정 시간이 든다.\n"
        "이 구상에서 가장 먼저 확인할 작은 실험: 한 과목의 일주일 자료로 검증한다.\n",
        option_id="opt-0-codex",
        agent="codex",
    )

    assert option["quality"]["status"] == "ready"
    assert option_is_synthesis_ready(option)


def test_unverified_repo_claim_makes_option_needs_review() -> None:
    option = parse_idea_option(
        "- **제목:** 제안\n"
        "- **핵심 원리:** 레포에 이미 파서가 구현되어 있다.\n"
        "- **사용 장면:** 검토\n"
        "- **차이:** 근거를 남긴다.\n"
        "- **tradeoff:** 느리다.\n"
        "- **첫 실험:** 파일 한 개를 비교한다.\n",
        option_id="opt-0-cursor",
        agent="cursor",
    )

    assert option["quality"]["status"] == "needs_review"
    assert option["quality"]["unverified_repo_claims"]
    assert not option_is_synthesis_ready(option)


def test_synthesis_block_exposes_selected_option_and_safety_boundary() -> None:
    run = {
        "ideation": {
            "options": [
                {
                    "id": "opt-0-codex",
                    "title": "근거형 노트",
                    "principle": "원문 위치를 보존한다.",
                    "usage": "시험 전 복습",
                    "difference": "근거를 남긴다.",
                    "tradeoff": "검토 시간이 든다.",
                    "first_experiment": "PDF 한 개로 비교한다.",
                    "quality": {"status": "ready", "contract": IDEATION_OUTPUT_CONTRACT},
                }
            ],
            "selection": {"option_id": "opt-0-codex"},
        }
    }
    block = ideation_synthesis_block(run)
    assert "selected_option_id: opt-0-codex" in block
    assert "근거형 노트" in block
    assert "unverified repository claim" in block


def test_synthesis_block_does_not_promote_blocked_option_fields() -> None:
    run = {
        "ideation": {
            "options": [
                {
                    "id": "opt-0-cursor",
                    "title": "레포에 이미 파서가 있다",
                    "principle": "레포에 이미 파서가 구현되어 있다.",
                    "usage": "검토",
                    "difference": "근거를 남긴다.",
                    "tradeoff": "느리다.",
                    "first_experiment": "파일 한 개를 비교한다.",
                    "quality": {
                        "status": "needs_review",
                        "missing_fields": [],
                        "unverified_repo_claims": ["레포에 이미 파서가 구현되어 있다."],
                    },
                }
            ],
            "selection": {"option_id": "opt-0-cursor"},
        }
    }
    block = ideation_synthesis_block(run)
    assert "selected_option_status: blocked_needs_review" in block
    assert "selected_option:\n- title:" not in block
    assert "review_required_repo_claims" in block
