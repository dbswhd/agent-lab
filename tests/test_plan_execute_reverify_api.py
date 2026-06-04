from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("LIVE_OK\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def test_execute_reverify_endpoint_records_mock_oracle(
    tmp_path: Path,
    monkeypatch,
):
    sessions_dir = tmp_path / "sessions"
    folder = sessions_dir / "sess-api"
    folder.mkdir(parents=True)
    repo = _init_repo(tmp_path / "repo")
    execution = {
        "id": "exec-api",
        "status": "merged",
        "isolation_effective": "worktree",
        "action_index": 1,
        "action_kind": "now",
        "action_what": "verify api",
        "action_where": "`src/app.py`",
        "action_verify": "`LIVE_OK`",
        "git_root": str(repo),
        "workspace_root": str(repo),
        "source_touched_paths": ["src/app.py"],
        "touched_paths": ["src/app.py"],
        "verify_retries": 0,
        "verify_history": [],
    }
    (folder / "run.json").write_text(
        json.dumps({"executions": [execution]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    from app.server.main import app

    client = TestClient(app)
    res = client.post(
        "/api/sessions/sess-api/execute/reverify",
        json={"execution_id": "exec-api"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["verify_after_merge"]["status"] == "passed"
    assert body["execution"]["verify_retries"] == 1
    assert body["execution"]["reverify_endpoint"] == (
        "/api/sessions/{session_id}/execute/reverify"
    )
    assert body["execution"]["oracle"]["verdict"] == "pass"
    assert body["execution"]["verify_after_merge"]["oracle"]["checked_paths"] == [
        "src/app.py"
    ]
