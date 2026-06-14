"""Communicate KPI helpers and hook communicate remaining tests."""

from __future__ import annotations

from pathlib import Path

from agent_lab.communicate_kpis import communicate_counts, communicate_scores
from agent_lab.reply_policy import envelope_follow_up_block, resolve_reply_policy
from agent_lab.room_hooks import (
    HookResult,
    _builtin_post_agent_reply_envelope_check,
    run_pre_scribe_hooks,
)


def test_communicate_counts_from_run_meta():
    run = {
        "turns": [
            {
                "communicate_meta": {
                    "agent_reply_count": 3,
                    "envelope_parse_error_count": 1,
                    "legacy_endorse_count": 0,
                    "guidance_chars": 1200,
                    "envelope_strict": True,
                }
            }
        ],
        "hook_runs": [{"blocked": True, "sub_reason": "envelope_invalid"}],
    }
    counts = communicate_counts(run)
    assert counts["agent_replies"] == 3
    assert counts["envelope_parse_errors"] == 1
    assert counts["hook_runs"] == 1
    scores = communicate_scores(counts)
    assert scores["envelope_parse_success_rate"] == 2 / 3


def test_communicate_counts_aggregate_act_counts():
    run = {
        "turns": [
            {
                "communicate_meta": {
                    "agent_reply_count": 3,
                    "act_counts": {"PROPOSE": 1, "CHALLENGE": 1, "ENDORSE": 1},
                }
            },
            {
                "communicate_meta": {
                    "agent_reply_count": 2,
                    "act_counts": {"ENDORSE": 1, "AMEND": 1},
                }
            },
        ],
    }
    counts = communicate_counts(run)
    assert counts["acts_total"] == {
        "PROPOSE": 1,
        "CHALLENGE": 1,
        "ENDORSE": 2,
        "AMEND": 1,
    }
    scores = communicate_scores(counts)
    assert scores["challenge_rate"] == 1 / 5
    assert scores["endorse_rate"] == 2 / 5
    assert scores["amend_rate"] == 1 / 5


def test_summarize_turn_meta_records_acts_by_round():
    from types import SimpleNamespace

    from agent_lab.reply_policy import summarize_turn_communicate_meta

    def _msg(agent: str, content: str, act: str | None, pr: int):
        return SimpleNamespace(
            role="agent",
            agent=agent,
            content=content,
            envelope={"act": act, "refs": []} if act else None,
            envelope_parse_error=False,
            parallel_round=pr,
        )

    msgs = [
        _msg("cursor", "제안", "PROPOSE", 1),
        _msg("codex", "반박", "CHALLENGE", 2),
        _msg("claude", "이의 없습니다", "ENDORSE", 2),
        _msg("cursor", "no envelope", None, 2),
    ]
    meta = summarize_turn_communicate_meta(msgs, None)
    assert meta["act_counts"] == {"PROPOSE": 1, "CHALLENGE": 1, "ENDORSE": 1}
    assert meta["acts_by_round"] == {
        "1": {"PROPOSE": 1},
        "2": {"CHALLENGE": 1, "ENDORSE": 1},
    }
    assert meta["agent_reply_count"] == 4


def test_envelope_follow_up_compact_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_GUIDANCE_TIER", raising=False)
    policy = resolve_reply_policy(parallel_round=2, consensus_mode=True)
    block = envelope_follow_up_block(policy, context="consensus")
    assert "ENDORSE/PASS → one-line body" in block
    assert "Invalid — fence body must be JSON" not in block


def test_builtin_envelope_check_blocks_missing_act():
    result = _builtin_post_agent_reply_envelope_check(
        parallel_round=2,
        consensus_mode=True,
        review_mode=False,
        turn_profile="discuss",
        envelope=None,
        envelope_parse_error=False,
    )
    assert isinstance(result, HookResult)
    assert result.blocked is True
    assert result.sub_reason == "envelope_invalid"
    assert result.retryable is True


def test_pre_scribe_hook_no_commands(tmp_path: Path):
    run = {"team_lead": "cursor"}
    result = run_pre_scribe_hooks(run, session_folder=tmp_path, session_id="s1")
    assert result.blocked is False


def test_weekly_report_includes_communicate_section():
    from agent_lab.session_score_weekly import format_weekly_report_markdown

    md = format_weekly_report_markdown(
        {
            "period": {"start": "2026-06-01", "end": "2026-06-07", "days": 7},
            "sessions_dir": "/tmp/sessions",
            "include_fixtures": True,
            "sessions": [],
            "aggregate": {
                "scores": {"envelope_parse_success_rate": 0.95},
                "counts": {
                    "communicate": {
                        "agent_replies": 20,
                        "envelope_parse_errors": 1,
                        "legacy_endorse_count": 0,
                        "guidance_chars_total": 5000,
                        "communicate_turns": 4,
                        "hook_runs": 2,
                        "hook_blocked": 0,
                    },
                    "capability_cwd": {},
                },
            },
            "m4_milestones": {"applicable_count": 0, "overall_pass": None},
            "live_ops_summary": {},
        }
    )
    assert "## Hook · Communicate" in md
    assert "Envelope parse success" in md
