from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from agent_lab.plan_actions import find_dry_run_action
from agent_lab.plan_execute import run_dry_run
from agent_lab.plan_pending import (
    PlanSnapshotRequired,
    approve_pending_plan,
    ensure_plan_snapshot_approved,
)


PLAN_MD = """## 지금 실행
1.
   - 무엇을: app.py를 수정한다.
   - 어디서: `src/app.py`
   - 검증: `src/app.py` 내용 확인
"""


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
    (path / "src" / "app.py").write_text("v1\nstable\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def _seed_approved_snapshot(folder: Path) -> None:
    action = find_dry_run_action(PLAN_MD, 1, kind="now")
    assert action is not None
    try:
        ensure_plan_snapshot_approved(folder, action, PLAN_MD)
    except PlanSnapshotRequired as exc:
        approve_pending_plan(folder, exc.pending_plan["id"])


def test_revise_pending_execution_replaces_diff_and_remains_approvable(
    tmp_path: Path,
    monkeypatch,
):
    sessions_dir = tmp_path / "sessions"
    folder = sessions_dir / "sess-revise"
    folder.mkdir(parents=True)
    repo = _init_repo(tmp_path / "repo")
    (folder / "plan.md").write_text(PLAN_MD, encoding="utf-8")
    (folder / "run.json").write_text("{}\n", encoding="utf-8")
    _seed_approved_snapshot(folder)

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    monkeypatch.setattr(
        "agent_lab.plan_execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (repo, {}),
    )

    def _initial(**kwargs):
        (Path(kwargs["cwd"]) / "src" / "app.py").write_text(
            "first draft\nkeep from first draft\n",
            encoding="utf-8",
        )
        return "VERIFICATION: PASS — first draft"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _initial)
    initial = run_dry_run(folder, action_index=1, permissions={})
    initial_worktree = Path(initial["worktree_path"])
    hunk_ref = next(
        line for line in str(initial["diff"]).splitlines() if line.startswith("@@")
    )

    seen: dict[str, str] = {}
    monkeypatch.setattr("agent_lab.agents.codex_agent.is_available", lambda: True)

    def _revise_codex(*_args, **kwargs):
        seen["prompt"] = str(kwargs["user"])
        cwd = Path(kwargs["permissions"]["_discuss_cwd"])
        path = cwd / "src" / "app.py"
        path.write_text(
            path.read_text(encoding="utf-8").replace("first draft", "revised draft", 1),
            encoding="utf-8",
        )
        return "VERIFICATION: PASS — revised requested hunk"

    monkeypatch.setattr("agent_lab.agents.codex_agent.respond", _revise_codex)
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    from app.server.main import app

    client = TestClient(app)
    response = client.post(
        f"/api/sessions/sess-revise/execute/pending-plans/{initial['id']}/revise",
        json={
            "comment": "이 hunk만 revised draft로 바꿔줘",
            "chunk_ref": hunk_ref,
            "executor": "codex",
        },
    )

    assert response.status_code == 200
    body = response.json()
    revised = body["execution"]
    assert revised["id"] != initial["id"]
    assert revised["status"] == "pending_approval"
    assert revised["executor"] == "codex"
    assert revised["revision_of"] == initial["id"]
    assert revised["revision_attempt"] == 1
    assert revised["revision_history"][0]["comment"].startswith("이 hunk만")
    assert "revised draft" in revised["diff"]
    assert "+first draft\n" not in revised["diff"]
    assert "keep from first draft" in revised["diff"]
    assert hunk_ref in seen["prompt"]
    assert "이 hunk만 revised draft로 바꿔줘" in seen["prompt"]
    assert body["superseded_execution"]["status"] == "superseded"
    assert not initial_worktree.exists()
    assert Path(revised["worktree_path"]).is_dir()
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "v1\nstable\n"

    approved = client.post(
        "/api/sessions/sess-revise/execute/resolve",
        json={"execution_id": revised["id"], "vote": "approve"},
    )
    assert approved.status_code == 200
    assert approved.json()["execution"]["status"] == "merged"
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == (
        "revised draft\nkeep from first draft\n"
    )


def test_revise_pending_execution_returns_409_when_not_pending(
    tmp_path: Path,
    monkeypatch,
):
    sessions_dir = tmp_path / "sessions"
    folder = sessions_dir / "sess-revise-409"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps({"executions": [{"id": "exec-done", "status": "merged"}]}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    from app.server.main import app

    response = TestClient(app).post(
        "/api/sessions/sess-revise-409/execute/pending-plans/exec-done/revise",
        json={"comment": "다시 수정"},
    )

    assert response.status_code == 409
    assert "not pending approval" in response.text
