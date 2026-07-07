"""N10a — correction harvester unit tests (mock-only, no real I/O beyond tmp_path)."""

from __future__ import annotations

import json

import pytest

from agent_lab.correction_harvester import (
    build_correction_record,
    detect_user_correction,
    handle_correction_rule_inbox_resolve,
    maybe_propose_correction_rule,
    promote_correction_rule,
    record_user_correction_outcome,
)
from agent_lab.feedback_advisor import MIN_SAMPLE
from agent_lab.run.meta import read_run_meta


def _write_run(folder, *, topic: str = "topic") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(json.dumps({"topic": topic, "turns": []}), encoding="utf-8")


def _write_chat(folder, content: str) -> None:
    row = {"role": "user", "agent": None, "content": content, "ts": "2026-07-06T00:00:00Z"}
    (folder / "chat.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")


# --- detection ---------------------------------------------------------------


@pytest.mark.parametrize(
    "content,expected_key",
    [
        ("한국어로 답변해줘", "language_reminder"),
        ("respond in Korean please", "language_reminder"),
        ("다시 해줘 제대로", "redo_request"),
        ("아니 그게 아니라 다른 파일이야", "negation_redirect"),
        ("retry", "retry_reflex"),
        ("재시도", "retry_reflex"),
        ("이건 완전히 새로운 요청이야", None),
        ("", None),
    ],
)
def test_detect_user_correction(content: str, expected_key: str | None) -> None:
    pattern = detect_user_correction(content)
    assert (pattern.key if pattern else None) == expected_key


# --- RECORD --------------------------------------------------------------------


def test_record_user_correction_outcome_appends_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CORRECTION_HARVESTER", "1")
    folder = tmp_path / "session"
    _write_run(folder)
    _write_chat(folder, "한국어로 답변해줘")
    monkeypatch.setattr(
        "agent_lab.outcome_harvester.outcomes_path", lambda root=None: tmp_path / ".agent-lab" / "outcomes.jsonl"
    )

    record_user_correction_outcome(folder, 1)

    ledger = (tmp_path / ".agent-lab" / "outcomes.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 1
    row = json.loads(ledger[0])
    assert row["phase"] == "user_correction"
    assert row["pattern_key"] == "language_reminder"
    assert row["session_id"] == "session"


def test_record_user_correction_outcome_noop_when_no_pattern(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CORRECTION_HARVESTER", "1")
    folder = tmp_path / "session"
    _write_run(folder)
    _write_chat(folder, "새로운 기능을 추가해줘")
    ledger_path = tmp_path / ".agent-lab" / "outcomes.jsonl"
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger_path)

    record_user_correction_outcome(folder, 1)

    assert not ledger_path.is_file()


def test_record_user_correction_outcome_flag_off_is_noop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CORRECTION_HARVESTER", "0")
    folder = tmp_path / "session"
    _write_run(folder)
    _write_chat(folder, "한국어로 답변해줘")
    ledger_path = tmp_path / ".agent-lab" / "outcomes.jsonl"
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger_path)

    record_user_correction_outcome(folder, 1)

    assert not ledger_path.is_file()


def test_record_user_correction_outcome_fails_open_on_missing_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_CORRECTION_HARVESTER", "1")
    folder = tmp_path / "does-not-exist"
    # No run.json / chat.jsonl written — must not raise.
    record_user_correction_outcome(folder, 1)


def test_build_correction_record_truncates_excerpt(tmp_path) -> None:
    folder = tmp_path / "session"
    folder.mkdir()
    pattern = detect_user_correction("retry")
    assert pattern is not None
    record = build_correction_record(folder, "topic", pattern, "x" * 500)
    assert len(record["excerpt"]) == 120
    assert record["phase"] == "user_correction"


# --- W2 rule promotion --------------------------------------------------------


def _append_correction_rows(ledger_path, pattern_key: str, session_ids: list[str]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        for sid in session_ids:
            fh.write(json.dumps({"phase": "user_correction", "pattern_key": pattern_key, "session_id": sid}) + "\n")


def test_maybe_propose_correction_rule_below_min_sample_is_noop(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / ".agent-lab" / "outcomes.jsonl"
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger_path)
    _append_correction_rows(ledger_path, "language_reminder", ["s1", "s2"])  # below MIN_SAMPLE=3

    folder = tmp_path / "s2"
    _write_run(folder)
    pattern = detect_user_correction("한국어로")
    assert pattern is not None

    result = maybe_propose_correction_rule(folder, pattern, root=tmp_path)
    assert result is None


def test_maybe_propose_correction_rule_creates_inbox_item_at_min_sample(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / ".agent-lab" / "outcomes.jsonl"
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger_path)
    session_ids = [f"s{i}" for i in range(MIN_SAMPLE)]
    _append_correction_rows(ledger_path, "language_reminder", session_ids)

    folder = tmp_path / session_ids[-1]
    _write_run(folder)
    pattern = detect_user_correction("한국어로")
    assert pattern is not None

    result = maybe_propose_correction_rule(folder, pattern, root=tmp_path)
    assert result is not None
    assert result["kind"] == "correction_rule"

    run = read_run_meta(folder)
    items = run.get("human_inbox") or []
    assert len(items) == 1
    assert items[0]["kind"] == "correction_rule"


def test_maybe_propose_correction_rule_only_proposes_once(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / ".agent-lab" / "outcomes.jsonl"
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger_path)
    session_ids = [f"s{i}" for i in range(MIN_SAMPLE + 2)]
    _append_correction_rows(ledger_path, "language_reminder", session_ids)

    folder = tmp_path / session_ids[-1]
    _write_run(folder)
    pattern = detect_user_correction("한국어로")
    assert pattern is not None

    first = maybe_propose_correction_rule(folder, pattern, root=tmp_path)
    second = maybe_propose_correction_rule(folder, pattern, root=tmp_path)
    assert first is not None
    assert second is None


# --- promote / reject ----------------------------------------------------------


def test_promote_correction_rule_writes_markdown(tmp_path) -> None:
    dest = promote_correction_rule("language_reminder", root=tmp_path, session_count=3)
    assert dest.is_file()
    text = dest.read_text(encoding="utf-8")
    assert "language_reminder" in text
    assert "한국어로 응답할 것" in text


def test_handle_correction_rule_inbox_resolve_approve_promotes(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / ".agent-lab" / "outcomes.jsonl"
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger_path)
    session_ids = [f"s{i}" for i in range(MIN_SAMPLE)]
    _append_correction_rows(ledger_path, "language_reminder", session_ids)

    folder = tmp_path / session_ids[-1]
    _write_run(folder)
    pattern = detect_user_correction("한국어로")
    assert pattern is not None
    item = maybe_propose_correction_rule(folder, pattern, root=tmp_path)
    assert item is not None

    handle_correction_rule_inbox_resolve(folder, item, selected=["approve"], status="resolved", root=tmp_path)

    rules_path = tmp_path / ".agent-lab" / "wisdom" / "correction_rules.md"
    assert rules_path.is_file()

    # Re-resolving must not duplicate — state already "promoted".
    second = maybe_propose_correction_rule(folder, pattern, root=tmp_path)
    assert second is None


def test_approve_proposes_rule_sync_only_when_flag_on(tmp_path, monkeypatch) -> None:
    from agent_lab.run.meta import read_run_meta

    ledger_path = tmp_path / ".agent-lab" / "outcomes.jsonl"
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger_path)
    session_ids = [f"s{i}" for i in range(MIN_SAMPLE)]
    _append_correction_rows(ledger_path, "language_reminder", session_ids)

    folder = tmp_path / session_ids[-1]
    _write_run(folder)
    pattern = detect_user_correction("한국어로")
    item = maybe_propose_correction_rule(folder, pattern, root=tmp_path)
    assert item is not None

    # default OFF — approving a correction rule must not propose external sync
    handle_correction_rule_inbox_resolve(folder, item, selected=["approve"], status="resolved", root=tmp_path)
    inbox = [i for i in read_run_meta(folder).get("human_inbox") or [] if i.get("kind") == "rule_sync"]
    assert inbox == []


def test_approve_proposes_rule_sync_when_flag_enabled(tmp_path, monkeypatch) -> None:
    from agent_lab.run.meta import read_run_meta

    monkeypatch.setenv("AGENT_LAB_RULE_SYNC", "1")
    ledger_path = tmp_path / ".agent-lab" / "outcomes.jsonl"
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger_path)
    session_ids = [f"s{i}" for i in range(MIN_SAMPLE)]
    _append_correction_rows(ledger_path, "language_reminder", session_ids)

    folder = tmp_path / session_ids[-1]
    _write_run(folder)
    pattern = detect_user_correction("한국어로")
    item = maybe_propose_correction_rule(folder, pattern, root=tmp_path)
    assert item is not None

    handle_correction_rule_inbox_resolve(folder, item, selected=["approve"], status="resolved", root=tmp_path)
    pending = [
        i
        for i in read_run_meta(folder).get("human_inbox") or []
        if i.get("kind") == "rule_sync" and i.get("status") == "pending"
    ]
    assert len(pending) == 1
    assert "language_reminder" in pending[0]["refs"]


def test_handle_correction_rule_inbox_resolve_reject_suppresses_future_proposals(tmp_path, monkeypatch) -> None:
    ledger_path = tmp_path / ".agent-lab" / "outcomes.jsonl"
    monkeypatch.setattr("agent_lab.outcome_harvester.outcomes_path", lambda root=None: ledger_path)
    session_ids = [f"s{i}" for i in range(MIN_SAMPLE)]
    _append_correction_rows(ledger_path, "language_reminder", session_ids)

    folder = tmp_path / session_ids[-1]
    _write_run(folder)
    pattern = detect_user_correction("한국어로")
    assert pattern is not None
    item = maybe_propose_correction_rule(folder, pattern, root=tmp_path)
    assert item is not None

    handle_correction_rule_inbox_resolve(folder, item, selected=["reject"], status="resolved", root=tmp_path)

    rules_path = tmp_path / ".agent-lab" / "wisdom" / "correction_rules.md"
    assert not rules_path.is_file()

    second = maybe_propose_correction_rule(folder, pattern, root=tmp_path)
    assert second is None
