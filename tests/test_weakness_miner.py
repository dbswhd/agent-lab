"""HS1 MINE — traces, memory preservation, weakness pattern mining (mock-only)."""

from __future__ import annotations

import json

from agent_lab.outcome_harvester import append_outcome
from agent_lab.weakness_miner import (
    MIN_PATTERN_SAMPLE,
    mine_weakness_patterns,
    trace_path,
    weakness_miner_enabled,
    write_turn_trace,
)

_TURN = {
    "agents": ["cursor", "codex", "claude"],
    "agent_parallel_rounds": 1,
    "consensus": {"status": "reached"},
    "category": {"value": "standard", "source": "heuristic"},
    "roles": {"cursor": "proposer", "codex": "executor", "claude": "critic"},
}


def _write_run(folder, *, objections=None, executions=None) -> None:
    folder.mkdir()
    run = {
        "topic": "x",
        "turns": [dict(_TURN)],
        "objections": objections or [],
        "executions": executions or [],
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")


# ---------------------------------------------------------------------------
# flag gating
# ---------------------------------------------------------------------------


def test_weakness_miner_enabled_default_off(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_WEAKNESS_MINER", raising=False)
    assert weakness_miner_enabled() is False
    monkeypatch.setenv("AGENT_LAB_WEAKNESS_MINER", "1")
    assert weakness_miner_enabled() is True
    monkeypatch.setenv("AGENT_LAB_WEAKNESS_MINER", "0")
    assert weakness_miner_enabled() is False


# ---------------------------------------------------------------------------
# HS1-3 — write_turn_trace
# ---------------------------------------------------------------------------


def test_write_turn_trace_noop_when_flag_off(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_WEAKNESS_MINER", raising=False)
    folder = tmp_path / "sess-a"
    _write_run(folder)

    result = write_turn_trace(folder, 1, root=tmp_path / "root")
    assert result is None
    assert not (tmp_path / "root").exists()


def test_write_turn_trace_writes_summary_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WEAKNESS_MINER", "1")
    folder = tmp_path / "sess-b"
    _write_run(folder, executions=[{"oracle": {"verdict": "skipped"}, "repair_history": []}])
    root = tmp_path / "root"

    result = write_turn_trace(folder, 1, root=root)
    assert result is not None
    assert result["turn_metrics"]["failure_tags"] == ["harness_infra"]

    path = trace_path("sess-b", 1, root=root)
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["session_id"] == "sess-b"
    assert on_disk["human_turn"] == 1
    assert on_disk["turn_metrics"]["primary_tag"] == "harness_infra"


def test_write_turn_trace_none_folder_or_no_turns(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WEAKNESS_MINER", "1")
    assert write_turn_trace(None, 1, root=tmp_path / "root") is None

    folder = tmp_path / "sess-empty"
    folder.mkdir()
    (folder / "run.json").write_text(json.dumps({"turns": []}), encoding="utf-8")
    assert write_turn_trace(folder, 1, root=tmp_path / "root") is None


# ---------------------------------------------------------------------------
# HS1-4 — memory_store preservation
# ---------------------------------------------------------------------------


def test_write_turn_trace_preserves_failure_in_memory_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WEAKNESS_MINER", "1")
    folder = tmp_path / "sess-c"
    _write_run(folder, executions=[{"oracle": {"verdict": "skipped"}, "repair_history": []}])
    root = tmp_path / "root"

    write_turn_trace(folder, 1, root=root)

    from agent_lab.memory_store import MemoryStore

    mem_path = root / ".agent-lab" / "memory" / "failures.jsonl"
    assert mem_path.is_file()
    store = MemoryStore()
    store.load(mem_path)
    keys = store.list_keys("failures/sess-c")
    assert keys == ["turn1:harness_infra"]
    entry = store.get("failures/sess-c", "turn1:harness_infra")
    assert entry["turn_metrics"]["primary_tag"] == "harness_infra"


def test_write_turn_trace_no_memory_write_when_clean(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WEAKNESS_MINER", "1")
    folder = tmp_path / "sess-d"
    _write_run(folder, executions=[{"oracle": {"verdict": "pass", "evidence": ["x"]}, "repair_history": []}])
    root = tmp_path / "root"

    write_turn_trace(folder, 1, root=root)

    mem_path = root / ".agent-lab" / "memory" / "failures.jsonl"
    assert not mem_path.exists()


# ---------------------------------------------------------------------------
# HS1-2/HS1-5 — mine_weakness_patterns
# ---------------------------------------------------------------------------


def _outcome_row(session_id: str, *, primary_tag: str | None, category: str = "standard") -> dict:
    return {
        "session_id": session_id,
        "category": category,
        "primary_tag": primary_tag,
        "failure_tags": [primary_tag] if primary_tag else [],
    }


def test_mine_weakness_patterns_empty_ledger(tmp_path) -> None:
    root = tmp_path / "root"
    report = mine_weakness_patterns(root)
    assert report == {"patterns": [], "min_pattern_sample": MIN_PATTERN_SAMPLE}


def test_mine_weakness_patterns_below_threshold_not_addressable(tmp_path) -> None:
    root = tmp_path / "root"
    for i in range(MIN_PATTERN_SAMPLE - 1):
        append_outcome(_outcome_row(f"sess-{i}", primary_tag="weak_taste"), root=root)

    report = mine_weakness_patterns(root)
    assert len(report["patterns"]) == 1
    pattern = report["patterns"][0]
    assert pattern["pattern_id"] == "fp:weak_taste:standard"
    assert pattern["recurrence_count"] == MIN_PATTERN_SAMPLE - 1
    assert pattern["addressable"] is False


def test_mine_weakness_patterns_crosses_threshold(tmp_path) -> None:
    root = tmp_path / "root"
    for i in range(MIN_PATTERN_SAMPLE):
        append_outcome(_outcome_row(f"sess-{i}", primary_tag="harness_infra"), root=root)

    report = mine_weakness_patterns(root)
    pattern = report["patterns"][0]
    assert pattern["recurrence_count"] == MIN_PATTERN_SAMPLE
    assert pattern["addressable"] is True


def test_mine_weakness_patterns_dedupes_same_session(tmp_path) -> None:
    """Repeated rows from ONE session don't fake a recurring pattern."""
    root = tmp_path / "root"
    for _ in range(MIN_PATTERN_SAMPLE + 2):
        append_outcome(_outcome_row("sess-repeat", primary_tag="weak_taste"), root=root)

    report = mine_weakness_patterns(root)
    pattern = report["patterns"][0]
    assert pattern["recurrence_count"] == 1
    assert pattern["addressable"] is False


def test_mine_weakness_patterns_rows_without_tag_excluded(tmp_path) -> None:
    root = tmp_path / "root"
    append_outcome(_outcome_row("sess-clean", primary_tag=None), root=root)

    report = mine_weakness_patterns(root)
    assert report["patterns"] == []


def test_mine_weakness_patterns_sorted_by_recurrence_desc(tmp_path) -> None:
    root = tmp_path / "root"
    for i in range(2):
        append_outcome(_outcome_row(f"sess-a{i}", primary_tag="weak_taste"), root=root)
    for i in range(4):
        append_outcome(_outcome_row(f"sess-b{i}", primary_tag="false_success"), root=root)

    report = mine_weakness_patterns(root)
    assert [p["pattern_id"] for p in report["patterns"]] == [
        "fp:false_success:standard",
        "fp:weak_taste:standard",
    ]
