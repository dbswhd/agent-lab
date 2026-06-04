"""PI-executed: archive merged diff under sessions/<id>/executed/."""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.plan_execute_merge import archive_executed_diff


def test_archive_executed_diff_writes_once(tmp_path: Path):
    session = tmp_path / "sess"
    session.mkdir()
    execution = {
        "id": "exec-1",
        "action_id": "a1",
        "action_index": 1,
        "diff": "diff --git a/x.py\n+line\n",
        "diff_stat": "1 file changed",
        "merge": {"commit_sha": "abc123", "completed_at": "2026-06-01T00:00:00Z"},
        "status": "merged",
    }
    path = archive_executed_diff(session, execution_id="exec-1", execution=execution)
    assert path is not None
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["execution_id"] == "exec-1"
    assert "diff" in data
    again = archive_executed_diff(session, execution_id="exec-1", execution=execution)
    assert again == path


def test_archive_skips_empty_diff(tmp_path: Path):
    session = tmp_path / "sess"
    session.mkdir()
    assert (
        archive_executed_diff(
            session,
            execution_id="exec-2",
            execution={"diff": "", "merge": {}},
        )
        is None
    )
