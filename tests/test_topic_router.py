"""Topic category routing — 분류기·에스컬레이션·합의 루프 통합 (P2)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from agent_mocks import patch_call_agent_reply

from agent_lab.topic_router import (
    batch_escalation_act,
    classify_topic,
    detect_task_type,
    escalate_route,
    resolve_topic_route,
    route_debate_last,
)


def _clear_router_env(monkeypatch) -> None:
    for key in (
        "AGENT_LAB_TOPIC_ROUTER",
        "AGENT_LAB_DEBATE_ROUNDS",
        "AGENT_LAB_MAX_CONSENSUS_ROUNDS",
        "AGENT_LAB_MAX_CONSENSUS_CALLS",
        "AGENT_LAB_CLARIFIER_MIN_CHARS",
    ):
        monkeypatch.delenv(key, raising=False)


# --- 분류기 ---------------------------------------------------------------


def test_marker_overrides_everything(monkeypatch):
    _clear_router_env(monkeypatch)
    route = resolve_topic_route("보안 마이그레이션 설계\n[cat: quick]", turn_profile="verified")
    assert route.category == "quick"
    assert route.source == "marker"


def test_profile_implies_category(monkeypatch):
    _clear_router_env(monkeypatch)
    assert (
        resolve_topic_route("아무 토픽이나 길게 쓴 일반 토론 주제입니다 — 충분히 길게.", turn_profile="quick").category
        == "quick"
    )
    assert resolve_topic_route("아무 토픽", turn_profile="verified").category == "critical"


def test_keyword_classification(monkeypatch):
    _clear_router_env(monkeypatch)
    assert classify_topic("세션 스토어 마이그레이션 전 보안 검토가 필요합니다")[0] == "critical"
    assert classify_topic("캐시 계층 아키텍처 트레이드오프를 비교해 주세요")[0] == "deep"
    assert classify_topic("README 오타 고쳐줘")[0] == "quick"


def test_trading_route_from_session_template(monkeypatch):
    _clear_router_env(monkeypatch)
    route = resolve_topic_route(
        "일반 토픽",
        session_template="trading-mission",
    )
    assert route.category == "trading"
    assert route.source == "session_template"
    assert route.quality_gate is True
    assert route.wisdom_in_context is True


def test_trading_keyword_classification(monkeypatch):
    _clear_router_env(monkeypatch)
    cat, _ = classify_topic("[Trading Mission — 장전] proposal batch 작성")
    assert cat == "trading"

    _clear_router_env(monkeypatch)
    cat, signals = classify_topic("이거 머지됐어?")
    assert cat == "quick"
    assert signals and signals[0].startswith("len:")
    long_topic = (
        "세 에이전트가 합의할 일반적인 작업 주제를 충분히 길게 설명하는 문장입니다. "
        "후속 작업 범위와 담당을 정해야 합니다."
    )
    assert classify_topic(long_topic)[0] == "standard"


def test_router_disabled_mirrors_legacy(monkeypatch):
    _clear_router_env(monkeypatch)
    monkeypatch.setenv("AGENT_LAB_TOPIC_ROUTER", "0")
    route = resolve_topic_route("보안 마이그레이션 설계")
    assert route.source == "disabled"
    assert route.debate_rounds == 4  # DEFAULT_DEBATE_ROUNDS
    assert route.max_rounds == 12
    assert route.max_calls == 30
    assert route.quality_gate is False
    assert route.recombination == "off"


def test_env_overrides_route_defaults(monkeypatch):
    _clear_router_env(monkeypatch)
    monkeypatch.setenv("AGENT_LAB_MAX_CONSENSUS_CALLS", "12")
    route = resolve_topic_route("캐시 아키텍처 설계 검토를 부탁합니다 — 트레이드오프 포함")
    assert route.category == "deep"
    assert route.max_calls == 12


# --- 라우팅 테이블 ---------------------------------------------------------


def test_route_budgets(monkeypatch):
    _clear_router_env(monkeypatch)
    quick = resolve_topic_route("오타 수정")
    assert (quick.debate_rounds, quick.max_rounds, quick.max_calls) == (0, 4, 9)
    assert route_debate_last(quick) == 1

    deep = resolve_topic_route("모듈 구조 재설계 아키텍처 논의 — 트레이드오프 비교 필수")
    assert deep.debate_rounds == 4
    assert deep.quality_gate is True
    assert deep.recombination == "on"
    assert deep.wisdom_in_context is True
    assert route_debate_last(deep) == 5


def test_critical_suggests_verified(monkeypatch):
    _clear_router_env(monkeypatch)
    route = resolve_topic_route("프로덕션 DB 마이그레이션 절차 결정")
    assert route.category == "critical"
    assert route.suggest_verified is True


# --- 에스컬레이션 -----------------------------------------------------------


def test_escalation_one_step_no_demote(monkeypatch):
    _clear_router_env(monkeypatch)
    quick = resolve_topic_route("오타 수정")
    up1 = escalate_route(quick, act="CHALLENGE")
    assert up1.category == "standard"
    assert up1.escalated_from == "quick"
    assert up1.escalation_act == "CHALLENGE"
    up2 = escalate_route(up1, act="AMEND")
    assert up2.category == "trading"
    assert up2.escalated_from == "quick"  # 최초 카테고리 보존
    up3 = escalate_route(up2, act="BLOCK")
    assert up3.category == "deep"
    up4 = escalate_route(up3, act="BLOCK")
    assert up4.category == "deep"  # deep에서 멈춤 (critical은 명시적만)


def test_escalation_disabled_route_noop(monkeypatch):
    _clear_router_env(monkeypatch)
    monkeypatch.setenv("AGENT_LAB_TOPIC_ROUTER", "0")
    route = resolve_topic_route("오타 수정")
    assert escalate_route(route, act="CHALLENGE") is route


def test_batch_escalation_act_priority():
    def _msg(act: str | None):
        return SimpleNamespace(envelope={"act": act} if act else None)

    assert batch_escalation_act([_msg("ENDORSE"), _msg(None)]) is None
    assert batch_escalation_act([_msg("AMEND"), _msg("CHALLENGE")]) == "CHALLENGE"
    assert batch_escalation_act([_msg("AMEND"), _msg("BLOCK")]) == "BLOCK"
    assert batch_escalation_act([_msg("AMEND")]) == "AMEND"


# --- 합의 루프 통합 (mock E2E) ----------------------------------------------


def _envelope_reply(act: str, body: str, refs: list[str] | None = None) -> str:
    env = json.dumps({"act": act, "refs": refs or [], "confidence": 0.9})
    return f"```agent-envelope\n{env}\n```\n{body}"


def test_quick_route_skips_debate(monkeypatch, tmp_path):
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    calls: list[tuple[str, int]] = []
    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        calls.append((agent, n))
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "단답: 머지 완료 상태입니다.")
        return _envelope_reply("ENDORSE", "이의 없습니다")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, _messages, _plan = room.run_room(
        "이거 머지됐어?\n[cat: quick]",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    turn = run["turns"][0]
    assert turn["category"]["value"] == "quick"
    assert turn["category"]["source"] == "marker"
    consensus = turn["consensus"]
    assert consensus["status"] == "reached"
    assert consensus["category"]["value"] == "quick"
    # debate 0회: R1 3콜 + endorse 확인만 — quick cap(9) 내, 호출 6회 이하
    assert len(calls) <= 6


def test_challenge_escalates_quick_turn(monkeypatch, tmp_path):
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    events: list[tuple[str, dict]] = []
    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "단순 rename으로 충분합니다.")
        if agent == "codex" and n == 1:
            return _envelope_reply("CHALLENGE", "rename만으론 호출부가 깨집니다 — 마이그레이션 경로 필요.")
        return _envelope_reply("ENDORSE", "이의 없습니다")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, _messages, _plan = room.run_room(
        "헬퍼 rename 하나만 — 오타 수준.\n[cat: quick]",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
        on_event=lambda typ, payload: events.append((typ, payload)),
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    turn = run["turns"][0]
    category = turn["category"]
    assert category["value"] == "standard"
    assert category["escalated_from"] == "quick"
    assert category["escalation_act"] == "CHALLENGE"
    assert turn["consensus"]["status"] == "reached"
    # 에스컬레이션 후 debate 라운드(R2~)가 실제로 돌았는지
    assert turn["consensus"]["rounds"] >= 3
    assert any(typ == "category_escalated" for typ, _ in events)


def test_router_off_keeps_legacy_loop(monkeypatch, tmp_path):
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.setenv("AGENT_LAB_TOPIC_ROUTER", "0")
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "제안 본문")
        return _envelope_reply("ENDORSE", "이의 없습니다")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, _messages, _plan = room.run_room(
        "이거 머지됐어?\n[cat: quick]",  # marker는 라우터 off면 무시
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    turn = run["turns"][0]
    assert turn["category"]["source"] == "disabled"
    # 레거시 debate 4라운드가 그대로 돈다 (R2~R5) → endorse는 R6+
    assert turn["consensus"]["rounds"] >= 6


# --- Expert Pool: 작업 유형 감지 & 에이전트 서브셋 -------------------------


def test_detect_task_type_code(monkeypatch):
    _clear_router_env(monkeypatch)
    assert detect_task_type("로그인 기능 구현해줘") == "code"
    assert detect_task_type("버그 fix해줘") == "code"
    assert detect_task_type("새 클래스 작성해") == "code"
    assert detect_task_type("테스트 작성해줘") == "code"


def test_detect_task_type_review(monkeypatch):
    _clear_router_env(monkeypatch)
    assert detect_task_type("이 코드 리뷰해줘") == "review"
    assert detect_task_type("PR 검토해 봐줘") == "review"
    assert detect_task_type("이 설계 의견 줘") == "review"


def test_detect_task_type_general(monkeypatch):
    _clear_router_env(monkeypatch)
    assert detect_task_type("이번 주 어떻게 할까?") == "general"
    assert detect_task_type("배포 일정 논의") == "general"


def test_agent_subset_code_standard(monkeypatch):
    """standard code → producer_reviewer topology; full team (subset cleared)."""
    _clear_router_env(monkeypatch)
    route = resolve_topic_route("로그인 API 구현해줘 — FastAPI 엔드포인트와 JWT 토큰 검증 로직을 추가해야 합니다.")
    assert route.category == "standard"
    assert route.task_type == "code"
    assert route.topology == "producer_reviewer"
    assert route.agent_subset is None
    assert route.category_dict()["topology"] == "producer_reviewer"


def test_agent_subset_review_standard(monkeypatch):
    """standard 카테고리 review 작업 → claude+codex 서브셋."""
    _clear_router_env(monkeypatch)
    route = resolve_topic_route("이 PR 코드 리뷰해줘 — 유저 프로필 업데이트 모듈 변경사항에 대해 피드백 부탁드립니다.")
    assert route.category == "standard"
    assert route.task_type == "review"
    assert route.agent_subset == ("claude", "codex")


def test_agent_subset_deep_is_none(monkeypatch):
    """deep/critical은 서브셋 없음 — 전원 참여."""
    _clear_router_env(monkeypatch)
    route = resolve_topic_route("전체 아키텍처 재설계 — 트레이드오프 비교 필수")
    assert route.category == "deep"
    assert route.agent_subset is None


def test_agent_subset_critical_is_none(monkeypatch):
    _clear_router_env(monkeypatch)
    route = resolve_topic_route("프로덕션 DB 마이그레이션 보안 검토")
    assert route.category == "critical"
    assert route.agent_subset is None


def test_escalation_releases_subset(monkeypatch):
    """에스컬레이션 시 agent_subset이 None으로 리셋된다."""
    _clear_router_env(monkeypatch)
    review_route = resolve_topic_route(
        "이 PR 코드 리뷰해줘 — 유저 프로필 업데이트 모듈 변경사항에 대해 피드백 부탁드립니다."
    )
    assert review_route.task_type == "review"
    assert review_route.agent_subset == ("claude", "codex")
    escalated = escalate_route(review_route, act="CHALLENGE")
    assert escalated.agent_subset is None


def test_agent_subset_applied_in_consensus_room(monkeypatch, tmp_path):
    """review 작업에서 claude+codex만 실제로 호출되는지 E2E 검증."""
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    called_agents: list[str] = []

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        called_agents.append(str(agent))
        if agent == "cursor":
            return _envelope_reply("PROPOSE", "구현 완료했습니다.")
        return _envelope_reply("ENDORSE", "이의 없습니다")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    topic = "이 PR 코드 리뷰해줘 — 유저 프로필 업데이트 모듈 변경사항에 대해 피드백 부탁드립니다."
    room.run_room(
        topic,
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )
    assert "cursor" not in called_agents, f"cursor가 review 서브셋 제외인데 호출됨: {called_agents}"
    assert "claude" in called_agents or "codex" in called_agents


def test_topology_code_standard_is_producer_reviewer(monkeypatch):
    _clear_router_env(monkeypatch)
    route = resolve_topic_route("로그인 기능 구현해줘 — FastAPI 엔드포인트와 JWT 토큰 검증 로직을 추가해야 합니다.")
    assert route.task_type == "code"
    assert route.topology == "producer_reviewer"


def test_topology_review_is_parallel(monkeypatch):
    _clear_router_env(monkeypatch)
    route = resolve_topic_route("이 PR 코드 리뷰해줘 — 유저 프로필 업데이트 모듈 변경사항에 대해 피드백 부탁드립니다.")
    assert route.task_type == "review"
    assert route.topology == "parallel"


def test_topology_legacy_specialist_profile(monkeypatch):
    _clear_router_env(monkeypatch)
    route = resolve_topic_route("짧은 질문", turn_profile="specialist")
    assert route.topology == "producer_reviewer"
