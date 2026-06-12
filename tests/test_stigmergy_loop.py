"""P5 — wisdom R1 주입 · [LEARNED:] 수확 · MCP wisdom_search · 창발 벤치(mock)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.agent_envelope import extract_learned_notes
from agent_lab.context_bundle import (
    _append_wisdom_search_block,
    wisdom_in_context_mode,
)


class _Msg:
    def __init__(self, role, agent=None, content="", parallel_round=1):
        self.role = role
        self.agent = agent
        self.content = content
        self.parallel_round = parallel_round
        self.envelope = None


# --- 5B [LEARNED:] ------------------------------------------------------------


def test_extract_learned_notes():
    text = "분석 결과입니다.\n[LEARNED: WAL 모드는 동시 쓰기 락을 줄인다]\n[LEARNED: ]"
    assert extract_learned_notes(text) == ["WAL 모드는 동시 쓰기 락을 줄인다"]
    assert extract_learned_notes("") == []


def test_harvest_agent_learnings_dedupe(tmp_path, monkeypatch, request):
    import shutil
    import uuid

    from agent_lab.mission_loop import ensure_mission_notepads, mission_notepad_dir
    from agent_lab.wisdom_index import harvest_agent_learnings

    monkeypatch.delenv("AGENT_LAB_AGENT_LEARNINGS", raising=False)
    # mission notepad는 ~/.agent-lab/missions/<폴더이름> 전역 경로 —
    # pytest 실행 간 tmp_path 이름이 반복되므로 uuid + cleanup으로 격리한다.
    folder = tmp_path / f"learn-{uuid.uuid4().hex[:10]}"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    ensure_mission_notepads(folder)
    request.addfinalizer(
        lambda: shutil.rmtree(mission_notepad_dir(folder), ignore_errors=True)
    )
    msgs = [
        _Msg("user", content="topic"),
        _Msg("agent", "codex", "[LEARNED: outbox 패턴이 장애 전파를 끊는다]"),
        _Msg("agent", "claude", "[LEARNED: outbox 패턴이 장애 전파를 끊는다]는 동의.\n"
             "[LEARNED: 핵심 지표는 스트림 분리가 싸다]"),
    ]
    added = harvest_agent_learnings(folder, msgs)
    assert added == 3  # codex 1 + claude 2 (에이전트 prefix 달라 별개 항목)
    text = (mission_notepad_dir(folder) / "learnings.md").read_text(encoding="utf-8")
    assert "[codex] outbox 패턴이 장애 전파를 끊는다" in text
    # 재수확은 dedupe
    assert harvest_agent_learnings(folder, msgs) == 0


def test_harvest_agent_learnings_flag_off(tmp_path, monkeypatch):
    from agent_lab.wisdom_index import harvest_agent_learnings

    monkeypatch.setenv("AGENT_LAB_AGENT_LEARNINGS", "0")
    msgs = [_Msg("user"), _Msg("agent", "codex", "[LEARNED: x]")]
    assert harvest_agent_learnings(tmp_path, msgs) == 0


# --- 5A wisdom R1 주입 ---------------------------------------------------------


@pytest.fixture
def wisdom_session(tmp_path: Path):
    """wisdom note 1건이 있는 세션 — 전역 notepad 경로를 uuid로 격리 + 정리."""
    import shutil
    import uuid

    from agent_lab.mission_loop import (
        append_wisdom_note,
        ensure_mission_notepads,
        mission_notepad_dir,
    )

    folder = tmp_path / f"sess-{uuid.uuid4().hex[:10]}"
    folder.mkdir()
    (folder / "run.json").write_text(
        json.dumps({"wisdom_index": {"enabled": True}}), encoding="utf-8"
    )
    ensure_mission_notepads(folder)
    append_wisdom_note(
        folder,
        line="outbox 패턴 재시도가 장애 전파를 끊는다 — 검증 완료",
        filename="learnings.md",
        auto_provenance=False,
    )
    yield folder
    shutil.rmtree(mission_notepad_dir(folder), ignore_errors=True)


def test_wisdom_block_injected_for_deep_r1(wisdom_session, monkeypatch):
    monkeypatch.delenv("AGENT_LAB_WISDOM_IN_CONTEXT", raising=False)
    monkeypatch.setenv("AGENT_LAB_WISDOM_INDEX", "1")
    folder = wisdom_session
    run_meta = {
        "_session_folder": str(folder),
        "_turn_category": {"value": "deep", "source": "heuristic", "signals": []},
        "wisdom_index": {"enabled": True},
    }
    out = _append_wisdom_search_block(
        "BASE", topic="outbox 장애 전파 재시도 결정", run_meta=run_meta, parallel_round=1
    )
    assert "[세션 위즈덤" in out
    assert "outbox" in out
    assert len(out) <= len("BASE") + 2 + 820  # ~800자 cap

    # R2에는 미주입
    r2 = _append_wisdom_search_block(
        "BASE", topic="outbox 장애 전파 재시도 결정", run_meta=run_meta, parallel_round=2
    )
    assert r2 == "BASE"


def test_wisdom_block_respects_route_and_override(wisdom_session, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_WISDOM_INDEX", "1")
    folder = wisdom_session
    base_meta = {
        "_session_folder": str(folder),
        "wisdom_index": {"enabled": True},
    }
    standard = {**base_meta, "_turn_category": {"value": "standard"}}

    monkeypatch.setenv("AGENT_LAB_WISDOM_IN_CONTEXT", "auto")
    assert wisdom_in_context_mode() == "auto"
    out = _append_wisdom_search_block(
        "BASE", topic="outbox 재시도", run_meta=standard, parallel_round=1
    )
    assert out == "BASE"  # auto: standard route는 off

    monkeypatch.setenv("AGENT_LAB_WISDOM_IN_CONTEXT", "1")
    forced = _append_wisdom_search_block(
        "BASE", topic="outbox 재시도", run_meta=standard, parallel_round=1
    )
    assert "[세션 위즈덤" in forced  # 전역 강제 on

    monkeypatch.setenv("AGENT_LAB_WISDOM_IN_CONTEXT", "0")
    deep = {**base_meta, "_turn_category": {"value": "deep"}}
    off = _append_wisdom_search_block(
        "BASE", topic="outbox 재시도", run_meta=deep, parallel_round=1
    )
    assert off == "BASE"  # 전역 강제 off


# --- 5C MCP wisdom_search ------------------------------------------------------


def test_mcp_wisdom_search_tool(wisdom_session, monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.setenv("AGENT_LAB_WISDOM_INDEX", "1")
    folder = wisdom_session
    monkeypatch.setenv("AGENT_LAB_SESSION_FOLDER", str(folder))
    from agent_lab.inbox_mcp_server import wisdom_search

    payload = wisdom_search("outbox 재시도", k=3)
    assert payload["enabled"] is True
    assert payload["hit_count"] >= 1
    assert any("outbox" in (h.get("snippet") or "") for h in payload["hits"])


# --- 5D 창발 벤치 (mock) --------------------------------------------------------


def test_emergence_bench_composite_and_aggregate():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "emergence_bench", Path(__file__).resolve().parents[1] / "scripts" / "emergence_bench.py"
    )
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)

    assert bench.composite_score({"hybrid_action_rate": 1.0, "duplicate_speech_rate": 0.0}) == 1.0
    assert bench.composite_score({}) is None

    rows = [
        {"category": "deep", "emergence_delta": 0.2},
        {"category": "deep", "emergence_delta": -0.1},
        {"category": "quick", "emergence_delta": None},
    ]
    agg = bench.aggregate_by_category(rows)
    assert agg["deep"]["topics"] == 2
    assert round(agg["deep"]["delta_mean"], 3) == 0.05
    assert agg["deep"]["delta_positive"] == 1
    assert agg["quick"]["delta_mean"] is None


def test_emergence_bench_mock_run(tmp_path, monkeypatch):
    """벤치 하니스 1토픽 mock 실행 — JSON 리포트와 delta 필드 산출."""
    import subprocess
    import sys

    from agent_lab.subprocess_env import subprocess_env

    topics = tmp_path / "topics.json"
    topics.write_text(
        json.dumps([{"category": "quick", "topic": "이거 머지됐어?\n[cat: quick]"}]),
        encoding="utf-8",
    )
    out = tmp_path / "report.json"
    env = subprocess_env(
        AGENT_LAB_MOCK_AGENTS="1",
        AGENT_LAB_CLARIFIER="0",
    )
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "emergence_bench.py"),
            "--topics",
            str(topics),
            "--out",
            str(out),
            "--sessions-base",
            str(tmp_path / "bench-sessions"),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
        cwd=str(root),
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["judge"] == "heuristic"
    assert report["mock"] is True
    row = report["topics"][0]
    assert row["category"] == "quick"
    assert len(row["solo"]) == 3
    assert "emergence_delta" in row
    assert "quick" in report["by_category"]
