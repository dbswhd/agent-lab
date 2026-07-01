"""Emergence KPIs — hybrid provenance, challenge yield, AMEND chains (P1)."""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.emergence_kpis import (
    act_distribution,
    amend_chain_depth,
    challenge_yield,
    emergence_kpis,
    hybrid_action_rate,
    load_chat_speakers,
    pure_challenge_yield,
    pure_challenge_yield_from_resolution,
    routing_kpis,
)
from agent_lab.session.score import score_session


def _write_chat(folder: Path, rows: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "chat.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def _agent(agent: str, content: str, *, act: str | None = None, pr: int = 1) -> dict:
    row: dict = {"role": "agent", "agent": agent, "content": content, "parallel_round": pr}
    if act:
        row["envelope"] = {"act": act, "refs": []}
    return row


def test_load_chat_speakers_numbering_matches_plan_refs(tmp_path: Path) -> None:
    folder = tmp_path / "s"
    _write_chat(
        folder,
        [
            {"role": "user", "content": "topic"},
            _agent("cursor", "proposal A"),
            _agent("codex", "proposal B"),
        ],
    )
    speakers = load_chat_speakers(folder / "chat.jsonl")
    assert speakers[0] == ("user", None)
    assert speakers[1] == ("agent", "cursor")
    assert speakers[2] == ("agent", "codex")


def test_hybrid_action_rate_two_agents(tmp_path: Path) -> None:
    folder = tmp_path / "s"
    _write_chat(
        folder,
        [
            {"role": "user", "content": "topic"},
            _agent("cursor", "use sqlite"),
            _agent("codex", "add retry"),
            _agent("claude", "이의 없습니다", act="ENDORSE", pr=2),
        ],
    )
    (folder / "plan.md").write_text(
        "## 지금 실행\n"
        "- sqlite + retry 통합 (ref: chat.jsonl#L2) (ref: chat.jsonl#L3)\n"
        "- 단독 제안 (ref: chat.jsonl#L2)\n"
        "- ref 없는 불릿\n",
        encoding="utf-8",
    )
    rate, counts = hybrid_action_rate(folder)
    assert counts == {"ref_bullets": 2, "hybrid_bullets": 1, "unresolved_refs": 0}
    assert rate == 0.5


def test_hybrid_action_rate_none_without_refs(tmp_path: Path) -> None:
    folder = tmp_path / "s"
    _write_chat(folder, [{"role": "user", "content": "x"}])
    (folder / "plan.md").write_text("## 합의\n- no refs\n", encoding="utf-8")
    rate, counts = hybrid_action_rate(folder)
    assert rate is None
    assert counts["ref_bullets"] == 0


def test_hybrid_action_rate_ignores_user_refs_and_out_of_range(tmp_path: Path) -> None:
    folder = tmp_path / "s"
    _write_chat(
        folder,
        [
            {"role": "user", "content": "topic"},
            _agent("cursor", "proposal"),
        ],
    )
    (folder / "plan.md").write_text(
        "- 사용자 ref만 (ref: chat.jsonl#L1)\n- 범위 밖 (ref: chat.jsonl#L99)\n- 단독 (ref: chat.jsonl#L2)\n",
        encoding="utf-8",
    )
    rate, counts = hybrid_action_rate(folder)
    assert counts["ref_bullets"] == 1
    assert counts["hybrid_bullets"] == 0
    assert counts["unresolved_refs"] == 1
    assert rate == 0.0


def test_challenge_yield_counts_resolutions() -> None:
    run = {
        "objections": [
            {"id": "obj-1", "from": "codex", "act": "CHALLENGE", "status": "resolved_accepted"},
            {"id": "obj-2", "from": "claude", "act": "BLOCK", "status": "open"},
            {"id": "obj-3", "from": "cursor", "act": "CHALLENGE", "status": "resolved_wontfix"},
        ]
    }
    rate, counts = challenge_yield(run)
    assert counts["total"] == 3
    assert counts["resolved_accepted"] == 1
    assert counts["open"] == 1
    assert rate == 1 / 3


def test_challenge_yield_none_when_no_conflict() -> None:
    rate, counts = challenge_yield({"objections": []})
    assert rate is None
    assert counts["total"] == 0


def test_pure_challenge_yield_excludes_block() -> None:
    run = {
        "objections": [
            {"id": "obj-1", "from": "codex", "act": "CHALLENGE", "status": "resolved_accepted"},
            {"id": "obj-2", "from": "claude", "act": "BLOCK", "status": "open"},
            {"id": "obj-3", "from": "cursor", "act": "CHALLENGE", "status": "open"},
        ]
    }
    rate, counts = pure_challenge_yield(run)
    assert counts["total"] == 2
    assert rate == 0.5


def test_pure_challenge_yield_from_resolution() -> None:
    rate, counts = pure_challenge_yield_from_resolution(
        {"CHALLENGE": {"accepted": 1, "wontfix": 0, "open": 2}}
    )
    assert counts["total"] == 3
    assert rate == 1 / 3


def test_amend_chain_depth_resets_per_turn() -> None:
    messages = [
        {"role": "user", "content": "t1"},
        {"role": "agent", "agent": "cursor", "envelope": {"act": "PROPOSE"}},
        {"role": "agent", "agent": "codex", "envelope": {"act": "AMEND"}},
        {"role": "agent", "agent": "claude", "envelope": {"act": "AMEND"}},
        {"role": "user", "content": "t2"},
        {"role": "agent", "agent": "codex", "envelope": {"act": "AMEND"}},
        {"role": "agent", "agent": "claude", "envelope": {"act": "ENDORSE"}},
    ]
    depth, counts = amend_chain_depth(messages)
    assert depth == 2.0
    assert counts == {"amend_total": 3, "max_chain_per_turn": 2}


def test_amend_chain_depth_none_without_envelopes() -> None:
    depth, counts = amend_chain_depth([{"role": "agent", "agent": "cursor", "content": "plain"}])
    assert depth is None
    assert counts["amend_total"] == 0


def test_act_distribution_counts_only() -> None:
    messages = [
        {"role": "agent", "agent": "cursor", "envelope": {"act": "PROPOSE"}},
        {"role": "agent", "agent": "codex", "envelope": {"act": "CHALLENGE"}},
        {"role": "agent", "agent": "claude", "envelope": {"act": "ENDORSE"}},
        {"role": "agent", "agent": "codex", "envelope": {"act": "ENDORSE"}},
        {"role": "user", "content": "no envelope"},
    ]
    assert act_distribution(messages) == {"PROPOSE": 1, "CHALLENGE": 1, "ENDORSE": 2}


def test_score_session_includes_emergence(tmp_path: Path) -> None:
    folder = tmp_path / "sess-emergence"
    _write_chat(
        folder,
        [
            {"role": "user", "content": "topic"},
            _agent("cursor", "use sqlite", act="PROPOSE"),
            _agent("codex", "add retry", act="AMEND", pr=2),
            _agent("claude", "이의 없습니다", act="ENDORSE", pr=3),
        ],
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "objections": [
                    {
                        "id": "obj-1",
                        "from": "codex",
                        "act": "CHALLENGE",
                        "status": "resolved_accepted",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "plan.md").write_text(
        "## 지금 실행\n- 통합안 (ref: chat.jsonl#L2) (ref: chat.jsonl#L3)\n",
        encoding="utf-8",
    )
    report = score_session(folder)
    assert report["scores"]["hybrid_action_rate"] == 1.0
    assert report["scores"]["challenge_yield"] == 1.0
    assert report["scores"]["amend_chain_depth_max"] == 1.0
    assert report["counts"]["emergence"]["acts"] == {
        "PROPOSE": 1,
        "AMEND": 1,
        "ENDORSE": 1,
    }
    assert any("hybrid plan actions" in line for line in report["summary_lines"])


def test_routing_kpis_escalation_and_savings() -> None:
    run = {
        "turns": [
            {
                "category": {"value": "quick", "source": "heuristic", "signals": []},
                "consensus": {"status": "reached", "calls": 5},
            },
            {
                "category": {
                    "value": "standard",
                    "source": "heuristic",
                    "signals": [],
                    "escalated_from": "quick",
                    "escalation_act": "CHALLENGE",
                },
                "consensus": {"status": "reached", "calls": 11},
            },
            {
                "category": {"value": "standard", "source": "heuristic", "signals": []},
                "consensus": {"status": "reached", "calls": 13},
            },
            {
                "category": {"value": "deep", "source": "marker", "signals": []},
                "consensus": {"status": "reached", "calls": 20},
            },
        ]
    }
    scores, counts = routing_kpis(run)
    assert counts["distribution"] == {"quick": 1, "standard": 2, "deep": 1}
    assert counts["auto_routed"] == 3  # marker 턴은 자동 라우팅이 아님
    assert counts["escalated"] == 1
    assert scores["escalation_rate"] == 1 / 3
    # standard 평균 12 − quick(비에스컬레이션) 평균 5 = 7
    assert scores["quick_call_savings"] == 7.0


def test_routing_kpis_none_without_categories() -> None:
    scores, counts = routing_kpis({"turns": [{"mode": "discuss"}]})
    assert scores["escalation_rate"] is None
    assert scores["quick_call_savings"] is None
    assert counts["distribution"] == {}


def test_emergence_kpis_bundle(tmp_path: Path) -> None:
    folder = tmp_path / "s"
    _write_chat(folder, [{"role": "user", "content": "x"}])
    (folder / "plan.md").write_text("- nothing\n", encoding="utf-8")
    scores, counts = emergence_kpis(folder, {}, [])
    assert scores == {
        "hybrid_action_rate": None,
        "challenge_yield": None,
        "pure_challenge_yield": None,
        "amend_chain_depth_max": None,
        "recombination_validity_rate": None,
        "dispatch_fanout_rate": None,
        "escalation_rate": None,
        "quick_call_savings": None,
    }
    assert counts["acts"] == {}
    assert counts["dispatch"]["total"] == 0
