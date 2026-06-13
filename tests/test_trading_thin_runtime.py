"""Tests for thin runtime session resolve + template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.session_setup import list_session_templates, template_guidance_block
from agent_lab.trading_mission.thin_runtime import (
    find_latest_trading_session,
    get_intraday_status,
    resolve_thin_session_folder,
)


def test_trading_thin_template_listed(monkeypatch):
    monkeypatch.setattr(
        "agent_lab.extensions.quant_trading.quant_pipeline_available",
        lambda: True,
    )
    ids = [t["id"] for t in list_session_templates()]
    assert "trading-thin" in ids


def test_thin_template_guidance_forbids_room():
    block = template_guidance_block("trading-thin")
    assert "no new Room" in block or "no new Room" in block.lower() or "Room" in block
    assert "get_intraday_status" in block


def test_find_latest_trading_session(tmp_path: Path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    for sess in (old, new):
        art = sess / "artifacts"
        art.mkdir(parents=True)
        (art / "proposal_batch.json").write_text("{}", encoding="utf-8")
    (new / "artifacts" / "proposal_batch.json").write_text(
        json.dumps({"mission_id": "new"}),
        encoding="utf-8",
    )
    found = find_latest_trading_session(base=tmp_path)
    assert found is not None
    assert found.name in {"old", "new"}


def test_resolve_thin_session_folder_latest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sess = tmp_path / "sess-thin"
    art = sess / "artifacts"
    art.mkdir(parents=True)
    (art / "market_snapshot.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("AGENT_LAB_SESSION_FOLDER", raising=False)
    monkeypatch.setattr(
        "agent_lab.trading_mission.thin_runtime.SESSIONS_DIR",
        tmp_path,
    )
    monkeypatch.setattr(
        "agent_lab.trading_mission.thin_runtime.find_latest_trading_session",
        lambda base=None: sess.resolve(),
    )
    assert resolve_thin_session_folder() == sess.resolve()


def test_get_intraday_status_mcp_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    session = tmp_path / "sess-intraday"
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "playbook.md").write_text(
        "# Trading\n\n## 오늘 장중 행동\n\n- approve only\n",
        encoding="utf-8",
    )
    (artifacts / "proposal_batch.json").write_text(
        json.dumps(
            {
                "mission_id": "2026-06-13-premarket",
                "ingest_ready": True,
                "proposals": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_LAB_SESSION_FOLDER", str(session))

    from agent_lab.research_mcp_server import get_intraday_status as mcp_status

    payload = mcp_status()
    assert payload.get("ok") is True
    assert payload.get("mission_id") == "2026-06-13-premarket"
    assert "full_room_discuss" in (payload.get("actions_forbidden") or [])
