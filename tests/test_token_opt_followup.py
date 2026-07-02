"""Tests for token optimization inbox follow-up helpers."""

from __future__ import annotations

from agent_lab.inbox.token_opt_followup import (
    TOKEN_OPT_DEFERRED_INBOX_ID,
    TOKEN_OPT_FOLLOWUP_QUESTIONS,
    resolve_deferred_token_opt_inbox,
)


def test_followup_questions_cover_claude_final_items():
    ids = {q["id"] for q in TOKEN_OPT_FOLLOWUP_QUESTIONS}
    assert "token-opt-p1-follow-budget" in ids
    assert "token-opt-p1-compact-tool" in ids
    assert "token-opt-harness-eval" in ids


def test_resolve_deferred_inbox_marks_resolved():
    inbox = [
        {"id": TOKEN_OPT_DEFERRED_INBOX_ID, "status": "deferred", "prompt": "constraints?"},
        {"id": "inbox-other", "status": "open", "prompt": "other"},
    ]
    out = resolve_deferred_token_opt_inbox(inbox)
    deferred = next(r for r in out if r["id"] == TOKEN_OPT_DEFERRED_INBOX_ID)
    assert deferred["status"] == "resolved"
    assert deferred["resolution"] == "token_opt_followup_materialized"
    other = next(r for r in out if r["id"] == "inbox-other")
    assert other["status"] == "open"
