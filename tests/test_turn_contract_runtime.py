from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_roles_contract_applies_quick_roster_and_round_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "0")
    monkeypatch.setenv("AGENT_LAB_INBOX_MODE", "soft")
    monkeypatch.setenv("AGENT_LAB_TURN_CONTRACT_MODE", "roles")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "outcomes"))

    from agent_lab import room

    folder, _, _ = room.run_room(
        "room.py에서 consensus 라운드 cap 기본값이 뭐야?",
        agents=["cursor", "codex", "claude"],
        synthesize=True,
        sessions_base=tmp_path / "sessions",
        consensus_mode=False,
        turn_profile="quick",
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    contract = run["turn_contract"]
    last_turn = run["turns"][-1]

    assert contract["contract_id"] == "quick_read"
    assert contract["applied"] is True
    assert contract["runtime_controls"] == {"agent_limit": 1, "max_rounds": 1, "consensus": False}
    assert last_turn["agents"] == ["cursor"]
    assert last_turn["agent_parallel_rounds"] == 1


def test_roles_contract_caps_guarded_consensus_rounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "0")
    monkeypatch.setenv("AGENT_LAB_INBOX_MODE", "soft")
    monkeypatch.setenv("AGENT_LAB_TURN_CONTRACT_MODE", "roles")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "outcomes"))

    from agent_lab import room

    folder, _, _ = room.run_room(
        "docs 오타 1건 수정 plan action을 만들어 dry-run 승인 merge Oracle PASS까지",
        agents=["cursor", "codex", "claude"],
        synthesize=True,
        sessions_base=tmp_path / "sessions",
        consensus_mode=False,
        turn_profile="quick",
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    contract = run["turn_contract"]
    last_turn = run["turns"][-1]

    assert contract["contract_id"] == "guarded_plan"
    assert contract["runtime_controls"]["max_rounds"] == 2
    assert last_turn["consensus_mode"] is True
    assert last_turn["agent_parallel_rounds"] <= 2


def test_adaptive_contract_applies_safety_floor_on_cold_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_CLARIFIER", "0")
    monkeypatch.setenv("AGENT_LAB_INBOX_MODE", "soft")
    monkeypatch.setenv("AGENT_LAB_TURN_CONTRACT_MODE", "adaptive")
    monkeypatch.setenv("AGENT_LAB_OUTCOMES_ROOT", str(tmp_path / "outcomes"))

    from agent_lab import room

    folder, _, _ = room.run_room(
        "금전 거래 코드에 위험이 없는지 봐줘",
        agents=["cursor", "codex", "claude"],
        synthesize=True,
        sessions_base=tmp_path / "sessions",
        consensus_mode=False,
        turn_profile="analyze",
    )
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    contract = run["turn_contract"]
    last_turn = run["turns"][-1]

    assert contract["source"] == "bootstrap"
    assert contract["applied"] is True
    assert contract["safety_floor"] == "critical_review"
    assert last_turn["consensus_mode"] is True
    assert last_turn["agent_parallel_rounds"] <= 2
