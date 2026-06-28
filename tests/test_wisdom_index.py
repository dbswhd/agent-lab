"""MB-10 — evidence + notepad wisdom index."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_lab.evidence_ledger import append_evidence
from agent_lab.mission.loop import append_wisdom_note, ensure_mission_notepads
from agent_lab.wisdom.index import (
    build_wisdom_index,
    public_wisdom_search_payload,
    search_wisdom_index,
    wisdom_index_enabled,
)


@pytest.fixture
def wisdom_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_WISDOM_INDEX", "1")


def test_wisdom_index_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_LAB_WISDOM_INDEX", raising=False)
    assert wisdom_index_enabled() is False
    assert wisdom_index_enabled({"mission_loop": {"enabled": True}}) is True


def test_build_and_search_index(tmp_path: Path, wisdom_on: None) -> None:
    folder = tmp_path / "sess-1"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    ensure_mission_notepads(folder)
    append_wisdom_note(folder, line="retry merge after verify failure", filename="learnings.md")
    append_evidence(
        folder,
        {"event": "dry_run", "detail": "oracle pending approval"},
    )
    index = build_wisdom_index(folder, force=True)
    assert index["document_count"] >= 2
    hits = search_wisdom_index(folder, "verify merge")
    assert hits
    assert any(hit.get("source") in {"evidence", "notepad"} for hit in hits)
    payload = public_wisdom_search_payload(folder, query="oracle")
    assert payload["enabled"] is True
    assert payload["hit_count"] >= 1


def test_index_rebuild_on_evidence_append(tmp_path: Path, wisdom_on: None) -> None:
    folder = tmp_path / "sess-2"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    append_evidence(folder, {"event": "merge", "detail": "approved by human"})
    from agent_lab.wisdom.index import index_path

    path = index_path(folder)
    assert path.is_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw.get("document_count", 0) >= 1
