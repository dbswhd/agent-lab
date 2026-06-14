"""DECISION-FORK parse + Inbox Facilitator (M4) — ref-anchored options, no invent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_lab.agent_envelope import parse_decision_forks
from agent_lab.inbox_facilitator import facilitate, merge_forks
from agent_lab.inbox_harvest import harvest_discuss_questions, harvest_question_candidates


def _fork_block(topic: str, options: list[tuple[str, list[str]]]) -> str:
    import json

    payload = {
        "topic": topic,
        "options": [{"label": label, "refs": refs} for label, refs in options],
    }
    return "토론 결과:\n```decision-fork\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


@dataclass
class _Msg:
    role: str
    agent: str | None = None
    content: str = ""
    envelope: dict[str, Any] | None = None


# --- parse_decision_forks ------------------------------------------------------


def test_parse_fork_with_options():
    text = _fork_block("cadence 스윕 범위", [("VU만", ["L42"]), ("VU+Theme", ["L51"])])
    forks = parse_decision_forks(text)
    assert len(forks) == 1
    assert forks[0].topic == "cadence 스윕 범위"
    assert len(forks[0].options) == 2
    assert forks[0].options[0].refs == ("L42",)


def test_parse_fork_malformed_json_skipped():
    text = "```decision-fork\n{not json}\n```"
    assert parse_decision_forks(text) == []


def test_parse_fork_requires_topic_and_options():
    import json

    no_topic = "```decision-fork\n" + json.dumps({"options": [{"label": "a", "refs": ["L1"]}]}) + "\n```"
    no_opts = "```decision-fork\n" + json.dumps({"topic": "t", "options": []}) + "\n```"
    assert parse_decision_forks(no_topic) == []
    assert parse_decision_forks(no_opts) == []


# --- merge_forks / facilitate --------------------------------------------------


def test_merge_drops_refless_options():
    forks = parse_decision_forks(
        _fork_block("scope", [("anchored", ["L1"]), ("invented", []), ("also-anchored", ["L2"])])
    )
    qs = merge_forks(forks)
    assert len(qs) == 1
    labels = [o["label"] for o in qs[0].options]
    assert "invented" not in labels  # ref-less dropped (no invent)
    assert labels == ["anchored", "also-anchored"]


def test_merge_skips_fork_with_under_two_anchored():
    forks = parse_decision_forks(_fork_block("scope", [("only-anchored", ["L1"]), ("refless", [])]))
    assert merge_forks(forks) == []  # < 2 surviving options → not a real fork


def test_merge_dedupes_and_unions_across_same_topic():
    forks = parse_decision_forks(_fork_block("scope", [("A", ["L1"]), ("B", ["L2"])])) + parse_decision_forks(
        _fork_block("scope", [("A", ["L3"]), ("C", ["L4"])])  # same topic, A dup + C new
    )
    qs = merge_forks(forks)
    assert len(qs) == 1
    labels = [o["label"] for o in qs[0].options]
    assert labels == ["A", "B", "C"]
    assert "L4" in qs[0].refs


def test_facilitate_no_forks_no_synthesis_by_default():
    assert facilitate([]) == []


def test_facilitate_injected_call_flows_through_ref_drop():
    block = _fork_block("scope", [("X", ["L9"]), ("Y", ["L8"]), ("Z", [])])

    def _call(_prompt: str) -> str:
        return block

    qs = facilitate([], prose_context="some debate", facilitator_call=_call)
    assert len(qs) == 1
    labels = [o["label"] for o in qs[0].options]
    assert labels == ["X", "Y"]  # injected synthesis still cannot keep ref-less Z


# --- harvest integration -------------------------------------------------------


def test_fork_candidate_has_options():
    messages = [
        _Msg(role="user", content="topic"),
        _Msg(
            role="agent",
            agent="claude",
            content=_fork_block("스윕 범위", [("VU만", ["L42"]), ("VU+Theme", ["L51"])]),
        ),
    ]
    cands = harvest_question_candidates(messages)
    assert any(c.trigger == "T-Q1" and len(c.options) == 2 for c in cands)


def test_harvest_creates_question_with_fork_options():
    run_meta: dict[str, Any] = {}
    messages = [
        _Msg(role="user", content="topic"),
        _Msg(
            role="agent",
            agent="codex",
            content=_fork_block("스윕 범위", [("VU만", ["L42"]), ("VU+Theme", ["L51"])]),
        ),
    ]
    created = harvest_discuss_questions(run_meta, messages, human_turn=1)
    fork_items = [i for i in created if i["options"]]
    assert len(fork_items) == 1
    item = fork_items[0]
    assert item["kind"] == "question"
    assert item["source"] == "orchestrator"
    assert item["trigger"] == "T-Q1"
    assert [o["label"] for o in item["options"]] == ["VU만", "VU+Theme"]
    assert all(o["refs"] for o in item["options"])  # every option anchored
