"""Telegram merge ingress — integration + optional live soak."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_mocks import disable_execute_inbox_mcp

from agent_lab.live_telegram_merge_soak import (
    SOAK_TELEGRAM_CHAT_ID,
    _write_soak_gateway_config,
    _write_soak_routes_config,
    run_live_telegram_merge_ingress_soak,
)
from agent_lab.plan.actions import find_dry_run_action
from agent_lab.plan.execute import run_dry_run
from agent_lab.plan.execute_git import detect_git_root
from agent_lab.plan.pending import PlanSnapshotRequired, approve_pending_plan, ensure_plan_snapshot_approved
from agent_lab.run.meta import read_run_meta
from app.server.main import app


@pytest.fixture(autouse=True)
def _isolate_run_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # try_begin_run() holds a real cross-process fcntl.flock at config_dir()/run.lock,
    # which collides across xdist workers without a private dir per test. See
    # tests/test_room_resume_stream.py's _isolate_run_lock / commit 2af5e735.
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(tmp_path / ".agent-lab-config"))


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("v1\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def _seed_plan(session: Path, plan_md: str) -> None:
    (session / "plan.md").write_text(plan_md, encoding="utf-8")
    action = find_dry_run_action(plan_md, 1, kind="now")
    assert action is not None
    try:
        ensure_plan_snapshot_approved(session, action, plan_md)
    except PlanSnapshotRequired as exc:
        approve_pending_plan(session, exc.pending_plan["id"])


def test_telegram_merge_ingress_webhook_integration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real HTTP webhook + resolve_execution merge path; Cursor dry-run stubbed only."""
    disable_execute_inbox_mcp(monkeypatch)
    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    parent = tmp_path / "soak-root"
    repo = _init_repo(parent / "repo")
    session = parent / "session"
    session.mkdir()
    (session / "run.json").write_text(
        json.dumps({"gate_profile": "assistant"}) + "\n",
        encoding="utf-8",
    )
    plan_md = """## 지금 실행
1.
   - 무엇을: app.py를 v2로 수정한다.
   - 어디서: `src/app.py`
   - 검증: `src/app.py` 내용 확인
"""
    _seed_plan(session, plan_md)

    config_dir = parent / "config"
    config_dir.mkdir()
    gw = config_dir / "gateway.toml"
    routes = config_dir / "routes.toml"
    _write_soak_gateway_config(gw)
    _write_soak_routes_config(routes, session_id=session.name)

    monkeypatch.setattr(session_mod, "SESSIONS_DIR", parent)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", parent)
    monkeypatch.setenv("AGENT_LAB_GATEWAY_CONFIG", str(gw))
    monkeypatch.setenv("AGENT_LAB_ROUTES_CONFIG", str(routes))

    def _respond(**kwargs):
        cwd = Path(kwargs["cwd"])
        assert detect_git_root(cwd) == cwd.resolve()
        (cwd / "src" / "app.py").write_text("v2\n", encoding="utf-8")
        return "VERIFICATION: PASS"

    monkeypatch.setattr("agent_lab.agents.cursor_agent.is_available", lambda: True)
    monkeypatch.setattr("agent_lab.agents.cursor_agent.respond", _respond)
    monkeypatch.setattr(
        "agent_lab.plan.execute.resolve_execute_workspace",
        lambda _permissions=None, _expected=None: (repo, {}),
    )

    execution = run_dry_run(session, action_index=1, permissions={})
    assert execution["status"] == "pending_approval"

    client = TestClient(app)
    response = client.post(
        "/api/gateway/telegram/webhook",
        json={
            "message": {
                "chat": {"id": SOAK_TELEGRAM_CHAT_ID},
                "text": "/approve merge",
            }
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("ok") is True
    assert "merge approved" in str(body.get("reply") or "").lower()
    assert body.get("route", {}).get("session_id") == session.name

    run = read_run_meta(session)
    row = next(r for r in run["executions"] if r["id"] == execution["id"])
    assert row["status"] == "merged"
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "v2\n"


@pytest.mark.live
def test_live_telegram_merge_ingress_soak_real_cursor(tmp_path: Path) -> None:
    if os.getenv("AGENT_LAB_RUN_LIVE", "").strip() not in {"1", "true", "yes"}:
        pytest.skip("set AGENT_LAB_RUN_LIVE=1 to run live Telegram merge ingress soak")
    from agent_lab.app_config import apply_config_env

    apply_config_env()
    report = run_live_telegram_merge_ingress_soak(work_parent=tmp_path, cleanup=False)
    if report["status"] == "skipped":
        pytest.skip(report.get("errors") or ["cursor unavailable"])
    assert report["status"] == "go", json.dumps(report, indent=2)
