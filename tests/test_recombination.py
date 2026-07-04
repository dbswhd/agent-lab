"""P4 — 재조합 라운드 + anchor 계보."""

from __future__ import annotations

import json

from agent_mocks import patch_call_agent_reply

from agent_lab.room.consensus import (
    ConsensusAnchor,
    consensus_follow_up,
    pick_anchor,
    recombination_follow_up,
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


class _Msg:
    def __init__(self, role, agent=None, content="", envelope=None, parallel_round=1):
        self.role = role
        self.agent = agent
        self.content = content
        self.envelope = envelope
        self.parallel_round = parallel_round


# --- 4A anchor 계보 ----------------------------------------------------------


def test_pick_anchor_chains_parent_id():
    msgs = [
        _Msg("agent", "cursor", "첫 제안 본문이 충분히 길어서 앵커 발췌가 됩니다.", {"act": "PROPOSE"}, 1),
    ]
    first = pick_anchor(msgs, ["cursor", "codex"], anchor_id="a1-1")
    assert first is not None
    assert first.id == "a1-1"
    assert first.parent_id is None
    assert first.to_dict()["id"] == "a1-1"
    assert "parent_id" not in first.to_dict()

    msgs.append(_Msg("agent", "codex", "수정안: 첫 제안에 검증 단계를 추가합니다.", {"act": "AMEND"}, 2))
    second = pick_anchor(msgs, ["cursor", "codex"], anchor_id="a1-2", prev_anchor=first)
    assert second is not None
    assert second.id == "a1-2"
    assert second.parent_id == "a1-1"
    assert second.to_dict()["parent_id"] == "a1-1"


def test_consensus_follow_up_echoes_anchor_id_and_delta():
    anchor = ConsensusAnchor(agent="codex", excerpt="수정안 발췌", parallel_round=3, id="a1-2", parent_id="a1-1")
    body = consensus_follow_up(anchor, amend_delta="직전 앵커(a1-1)를 보완·대체한 수정안입니다.")
    assert "a1-2" in body
    assert "변경점" in body
    plain = consensus_follow_up(ConsensusAnchor(agent="codex", excerpt="x", parallel_round=1))
    assert "앵커 id" not in plain
    assert "변경점" not in plain


def test_recombination_follow_up_requires_two_refs():
    body = recombination_follow_up()
    assert "2명 이상" in body
    assert "refs" in body


# --- 합성 검증 헬퍼 ----------------------------------------------------------


def test_is_valid_synthesis_resolves_ref_authors():
    from agent_lab.room import ChatMessage
    from agent_lab.room.messages import _is_valid_synthesis

    thread = [
        ChatMessage(role="user", agent=None, content="topic"),
        ChatMessage(role="agent", agent="cursor", content="제안 A", parallel_round=1),
        ChatMessage(role="agent", agent="codex", content="제안 B", parallel_round=1),
        ChatMessage(role="agent", agent="claude", content="제안 C", parallel_round=1),
    ]
    good = ChatMessage(
        role="agent",
        agent="claude",
        content="합성안",
        envelope={"act": "AMEND", "refs": ["L2", "chat.jsonl#L3"]},
        parallel_round=6,
    )
    assert _is_valid_synthesis(good, thread) is True

    self_ref = ChatMessage(
        role="agent",
        agent="claude",
        content="자기 인용",
        envelope={"act": "AMEND", "refs": ["L2", "L4"]},  # L4 = 본인
        parallel_round=6,
    )
    assert _is_valid_synthesis(self_ref, thread) is False

    endorse = ChatMessage(
        role="agent",
        agent="claude",
        content="이의 없습니다",
        envelope={"act": "ENDORSE", "refs": ["L2", "L3"]},
        parallel_round=6,
    )
    assert _is_valid_synthesis(endorse, thread) is False


# --- KPI ---------------------------------------------------------------------


def test_recombination_and_lineage_kpis():
    from agent_lab.emergence_kpis import anchor_chain_depth, recombination_kpis

    run = {
        "turns": [
            {
                "consensus": {
                    "status": "reached",
                    "recombination": {"round": 6, "replies": 3, "valid_syntheses": 2},
                    "anchor_lineage": [
                        {"id": "a1-1", "agent": "cursor"},
                        {"id": "a1-2", "agent": "claude", "parent_id": "a1-1"},
                    ],
                }
            },
            {"consensus": {"status": "reached", "recombination": {"skipped": "single_proposer"}}},
        ]
    }
    rate, counts = recombination_kpis(run)
    assert rate == 2 / 3
    assert counts["rounds_run"] == 1
    assert counts["skipped"] == 1

    depth, dcounts = anchor_chain_depth(run)
    assert depth == 1.0
    assert dcounts["turns_with_lineage"] == 1

    assert recombination_kpis({"turns": []})[0] is None
    assert anchor_chain_depth({"turns": []})[0] is None


# --- 합의 루프 통합 (mock E2E) ----------------------------------------------


def _envelope_reply(act: str, body: str, refs: list[str] | None = None) -> str:
    env = json.dumps({"act": act, "refs": refs or [], "confidence": 0.9})
    return f"```agent-envelope\n{env}\n```\n{body}"


def test_deep_route_runs_recombination_round(monkeypatch, tmp_path):
    """deep: debate 충돌 후 재조합 라운드 — 합성안이 새 앵커가 된다."""
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    monkeypatch.setenv("AGENT_LAB_INBOX_MODE", "soft")
    per_agent: dict[str, int] = {}

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if "재조합 라운드" in (user or ""):
            if agent == "claude":
                return _envelope_reply(
                    "AMEND",
                    "합성안: cursor의 단순 구조에 codex의 재시도 경로를 결합.",
                    refs=["L2", "L3", "L4"],
                )
            return _envelope_reply("ENDORSE", "이의 없습니다")
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "단순 직접 호출 구조로 갑니다.")
        if agent == "codex" and n == 2:
            return _envelope_reply("CHALLENGE", "재시도 경로가 없습니다 — outbox 필요.")
        return _envelope_reply("ENDORSE", "이의 없습니다")

    patch_call_agent_reply(monkeypatch, fake_call_agent)
    monkeypatch.setattr(room, "model_label", lambda agent: f"{agent}-model")

    folder, _messages, _plan = room.run_room(
        "이벤트 경로 아키텍처 결정.\n[cat: deep]",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=tmp_path,
        consensus_mode=True,
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    consensus = run["turns"][0]["consensus"]
    assert consensus["status"] == "reached"
    recomb = consensus["recombination"]
    assert recomb["replies"] == 3
    assert recomb["valid_syntheses"] >= 1
    # 합성안(가장 최근 실질 발화)이 앵커 — 재조합 라운드와 앵커 라운드 일치
    assert consensus["anchor"]["parallel_round"] == recomb["round"]
    assert consensus["anchor"]["id"]
    assert consensus["anchor_lineage"]

    from agent_lab.emergence_kpis import recombination_kpis

    rate, _counts = recombination_kpis(run)
    assert rate is not None and rate >= 1 / 3


def test_standard_single_proposer_skips_recombination(monkeypatch, tmp_path):
    """standard(auto): 실질 제안자 1명이면 재조합 skip — 사유 기록."""
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    per_agent: dict[str, int] = {}
    recomb_calls: list[str] = []

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        n = per_agent.get(agent, 0) + 1
        per_agent[agent] = n
        if "재조합 라운드" in (user or ""):
            recomb_calls.append(agent)
            return _envelope_reply("ENDORSE", "이의 없습니다")
        if agent == "cursor" and n == 1:
            return _envelope_reply("PROPOSE", "주간 리포트 포맷은 현행 유지가 좋겠습니다.")
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
    assert consensus["recombination"] == {"skipped": "single_proposer"}
    assert recomb_calls == []


def test_quick_route_has_no_recombination(monkeypatch, tmp_path):
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
    consensus = run["turns"][0]["consensus"]
    assert consensus["status"] == "reached"
    assert "recombination" not in consensus


def test_explicit_multi_select_survives_quick_route(monkeypatch, tmp_path):
    """사용자가 여러 에이전트를 명시 선택하면 quick 카테고리 단일 축소를 건너뛰고
    선택한 plugin 전원이 실제로 호출된다 (run.json agents도 마지막 1명으로 줄지 않음)."""
    from agent_lab import room

    _clear_router_env(monkeypatch)
    monkeypatch.delenv("AGENT_LAB_CLARIFIER", raising=False)
    spoke: set[str] = set()

    def fake_call_agent(agent, _system, user, **kwargs):
        if kwargs.get("scribe"):
            return "## Plan\n\n- mock\n"
        spoke.add(agent)
        if agent == "cursor":
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
    # quick 단일 축소가 적용됐다면 cursor 1명만 발화했을 것 — 명시 선택 3명 전원이 발화해야 한다.
    assert spoke == {"cursor", "codex", "claude"}
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert set(run["agents"]) == {"cursor", "codex", "claude"}
