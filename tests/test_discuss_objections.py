"""P3 — 충돌의 상태화: discuss objection 자동 해소·품질 게이트·수렴 프롬프트."""

from __future__ import annotations

import inspect
import json

from agent_mocks import patch_call_agent_reply

from agent_lab.room_objections import (
    append_objection,
    list_objections,
    open_objections,
    resolve_objections_on_endorse,
)


def _clear_router_env(monkeypatch) -> None:
    for key in (
        "AGENT_LAB_TOPIC_ROUTER",
        "AGENT_LAB_DISCUSS_OBJECTIONS",
        "AGENT_LAB_DEBATE_ROUNDS",
        "AGENT_LAB_MAX_CONSENSUS_ROUNDS",
        "AGENT_LAB_MAX_CONSENSUS_CALLS",
        "AGENT_LAB_CLARIFIER_MIN_CHARS",
    ):
        monkeypatch.delenv(key, raising=False)


# --- resolve_objections_on_endorse 단위 -------------------------------------


def test_endorse_resolves_own_discuss_challenge():
    meta: dict = {}
    append_objection(
        meta,
        from_agent="codex",
        act="CHALLENGE",
        body="재시도 경로 없음",
        human_turn=1,
        mode="discuss",
    )
    resolved = resolve_objections_on_endorse(meta, "codex", human_turn=1)
    assert len(resolved) == 1
    row = list_objections(meta)[0]
    assert row["status"] == "resolved_accepted"
    assert row["resolution"] == "challenger_endorsed_anchor"
    assert row["resolved_by"] == "codex"
    assert open_objections(meta) == []


def test_endorse_does_not_resolve_block_or_plan_or_other_agent():
    meta: dict = {}
    append_objection(meta, from_agent="codex", act="BLOCK", body="비가역 위험", human_turn=1, mode="discuss")
    append_objection(meta, from_agent="codex", act="CHALLENGE", body="plan 모드 충돌", human_turn=1, mode="plan")
    append_objection(meta, from_agent="claude", act="CHALLENGE", body="남의 충돌", human_turn=1, mode="discuss")
    assert resolve_objections_on_endorse(meta, "codex", human_turn=1) == []
    assert len(open_objections(meta)) == 3


def test_resolved_objection_not_recreated_by_reharvest():
    """턴 종료 재수확이 endorse로 해소된 충돌을 다시 열면 합의 게이트가 교착한다."""
    meta: dict = {}
    append_objection(meta, from_agent="codex", act="CHALLENGE", body="같은 충돌", human_turn=1, mode="discuss")
    resolve_objections_on_endorse(meta, "codex")
    again = append_objection(meta, from_agent="codex", act="CHALLENGE", body="같은 충돌", human_turn=1, mode="discuss")
    assert again is not None
    assert again["status"] == "resolved_accepted"  # 기존 행 반환, 재개 없음
    assert open_objections(meta) == []


# --- 수렴 프롬프트 (3B) ------------------------------------------------------


def test_convergence_prompt_rewards_dissent():
    from agent_lab import context_bundle

    src = inspect.getsource(context_bundle)
    assert "새 쟁점을 열기보다" not in src
    assert "결과를 바꾸는 이견이 가치입니다" in src


# --- 합의 루프 통합 (mock E2E) ----------------------------------------------


def _envelope_reply(act: str, body: str, refs: list[str] | None = None) -> str:
    env = json.dumps({"act": act, "refs": refs or [], "confidence": 0.9})
    return f"```agent-envelope\n{env}\n```\n{body}"


def test_discuss_challenge_resolved_in_consensus_loop(monkeypatch, tmp_path):
    """CHALLENGE → 도전자 수정안이 앵커 → 전원 동의 → 자동 해소 + challenge_yield 1.0."""
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "직접 호출 유지가 단순합니다.")
        if agent == "codex" and n == 2:
            return _envelope_reply("CHALLENGE", "직접 호출 유지는 재시도 경로가 없습니다 — outbox가 필요합니다.")
        return _envelope_reply("ENDORSE", "이의 없습니다")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, _messages, _plan = room.run_room(
        "이벤트 처리 경로를 정리합시다 — 직접 호출과 큐 방식 중 무엇으로 갈지 결정 필요.",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["turns"][0]["consensus"]["status"] == "reached"
    rows = [o for o in run.get("objections") or [] if o.get("act") == "CHALLENGE"]
    assert rows, "discuss CHALLENGE가 objections에 등록되어야 한다"
    assert all(o["status"] == "resolved_accepted" for o in rows)
    assert all(o["mode"] == "discuss" for o in rows)
    assert all(str(o.get("resolution") or "").startswith("challenger_") for o in rows)

    from agent_lab.emergence_kpis import challenge_yield

    rate, counts = challenge_yield(run)
    assert rate == 1.0
    assert counts["total"] >= 1


def test_quality_gate_forces_review_on_quiet_deep_debate(monkeypatch, tmp_path):
    """deep 토픽이 무충돌 수렴하면 합의 전 강제 反 라운드 1회."""
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    events: list[str] = []
    forced_calls: list[str] = []
    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if "품질 게이트" in (user or ""):
            forced_calls.append(agent)
            return _envelope_reply("CHALLENGE", "가장 약한 가정: 단일 리전 전제 — 멀티 리전 장애 시나리오 누락.")
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "캐시 계층은 단일 리전 redis로 갑니다.")
        return _envelope_reply("ENDORSE", "이의 없습니다")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, _messages, _plan = room.run_room(
        "캐시 계층 아키텍처 트레이드오프를 비교해 결정합시다.\n[cat: deep]",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
        on_event=lambda typ, _payload: events.append(typ),
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    consensus = run["turns"][0]["consensus"]
    assert consensus["status"] == "reached"
    quality = consensus["quality"]
    assert quality["forced_review"] is True
    assert quality["debate_challenges"] == 0
    assert quality["category"] == "deep"
    assert quality["forced_review_act"] == "CHALLENGE"
    assert len(forced_calls) == 1
    assert "quality_gate_review" in events


def test_quality_gate_skipped_when_debate_had_conflict(monkeypatch, tmp_path):
    """debate에 실질 충돌이 있으면 강제 反 없음 — quality는 항상 기록."""
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    # deep은 에스컬레이션이 없어 AMEND가 M3 inbox 질문으로 sync pause됨 — 게이트 검증에 집중
    monkeypatch.setenv("AGENT_LAB_INBOX_MODE", "soft")
    forced_calls: list[str] = []
    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if "품질 게이트" in (user or ""):
            forced_calls.append(agent)
            return _envelope_reply("ENDORSE", "이의 없습니다")
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "단일 리전 redis로 갑니다.")
        if agent == "codex" and n == 2:
            return _envelope_reply("AMEND", "리전 장애 대비 read-replica 1개 추가.")
        return _envelope_reply("ENDORSE", "이의 없습니다")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, _messages, _plan = room.run_room(
        "캐시 계층 아키텍처 트레이드오프를 비교해 결정합시다.\n[cat: deep]",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    consensus = run["turns"][0]["consensus"]
    assert consensus["status"] == "reached"
    quality = consensus["quality"]
    assert quality["forced_review"] is False
    assert quality["debate_challenges"] >= 1
    assert forced_calls == []


def test_quality_gate_off_for_standard_category(monkeypatch, tmp_path):
    """standard 라우팅은 품질 게이트 비활성 — 무충돌이어도 강제 反 없음."""
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    forced_calls: list[str] = []
    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if "품질 게이트" in (user or ""):
            forced_calls.append(agent)
            return _envelope_reply("ENDORSE", "이의 없습니다")
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "주간 리포트 포맷은 현행 유지.")
        return _envelope_reply("ENDORSE", "이의 없습니다")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, _messages, _plan = room.run_room(
        "주간 리포트 포맷을 어떻게 가져갈지 팀 차원에서 정리해 봅시다. "
        "섹션 구성과 공유 주기, 담당 로테이션까지 함께 정하면 좋겠습니다.",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    turn = run["turns"][0]
    assert turn["category"]["value"] == "standard"
    consensus = turn["consensus"]
    assert consensus["status"] == "reached"
    assert consensus["quality"]["forced_review"] is False
    assert forced_calls == []
