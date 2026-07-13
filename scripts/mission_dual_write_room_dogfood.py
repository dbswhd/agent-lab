"""Human cutover 판정용: 실제 Room 턴(멀티에이전트 mock) → production route dual-write dogfood.

이전 evidence(scripts/mission_dual_write_route_cohort.py)는 loop에서 직접 손으로 만든 plan.md/
run.json fixture로 route를 exercise했다. 이 스크립트는 대신 실제 ``agent_lab.room.run_room()``
파이프라인(peer discussion → plan synthesis, mock agents)으로 세션을 만든 뒤, 그 세션에 대해
production route(plan/approve, execute/resolve)를 dual-write ON 상태로 호출한다 — "합성
스크립트 트래픽"이 아니라 실제 Room이 만든 세션에 대한 dogfood 증거를 남기기 위함이다.

``scripts/x2_lift_dogfood_run.py``와 동일한 mock 관례(AGENT_LAB_MOCK_AGENTS, isolated config
dir, synthesize_plan patch로 파싱 가능한 plan 보장)를 따르되, 그 스크립트가 추적하는
``docs/_dogfood/x2-lift.md`` fixture는 건드리지 않는다(별도 topic 사용).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SAMPLE_PLAN = """# Dual-write dogfood feature

## 지금 실행

1. Add dogfood marker
   - 무엇을: implement dogfood marker
   - 어디서: `src/dogfood_marker.py`
   - 검증: `pytest tests/test_dogfood_marker.py`
"""


@contextmanager
def _isolated_config_dir() -> Any:
    previous = os.environ.get("AGENT_LAB_CONFIG_DIR")
    with tempfile.TemporaryDirectory(prefix="dualwrite-room-dogfood-config-") as tmp:
        os.environ["AGENT_LAB_CONFIG_DIR"] = tmp
        try:
            yield Path(tmp)
        finally:
            if previous is None:
                os.environ.pop("AGENT_LAB_CONFIG_DIR", None)
            else:
                os.environ["AGENT_LAB_CONFIG_DIR"] = previous


def _client(sessions_root: Path) -> Any:
    from fastapi.testclient import TestClient
    from agent_lab.session import paths as session_paths
    from agent_lab import session as session_module
    import app.server.deps as deps_mod
    from app.server.main import create_app

    session_paths.SESSIONS_DIR = sessions_root
    session_module.SESSIONS_DIR = sessions_root
    deps_mod.SESSIONS_DIR = sessions_root
    return TestClient(create_app(bootstrap=False))


def _read_model(client: Any, session_id: str) -> dict[str, Any]:
    response = client.get(f"/api/sessions/{session_id}/mission/read-model")
    response.raise_for_status()
    return response.json()


def _run_one_dogfood_session(sessions_root: Path, topic: str) -> dict[str, Any]:
    from agent_lab.plan.workflow_state import set_plan_workflow_phase
    from agent_lab.run.meta import read_run_meta

    peer_calls = {"n": 0}

    def _fake_peer_review(_folder: Path, *_args: object, **_kwargs: object) -> list[object]:
        peer_calls["n"] += 1
        return []

    def _fake_synthesize_plan(*_args: object, **_kwargs: object) -> str:
        return SAMPLE_PLAN

    with (
        patch("agent_lab.plan.workflow.run_plan_peer_review_round", _fake_peer_review),
        patch("agent_lab.room.synthesize_plan", _fake_synthesize_plan),
    ):
        from agent_lab import room

        folder, messages, plan_md = room.run_room(
            topic,
            agents=["cursor", "codex", "claude"],
            synthesize=True,
            sessions_base=sessions_root,
            turn_profile="loop",
        )

    session_id = folder.name
    run = read_run_meta(folder)
    turns = run.get("turns") or []
    agent_message_count = sum(1 for m in messages if getattr(m, "role", None) not in ("human", None))

    pw_phase_before = (run.get("plan_workflow") or {}).get("phase")
    if pw_phase_before not in {"HUMAN_PENDING", "APPROVED"}:
        set_plan_workflow_phase(folder, "HUMAN_PENDING")
    plan_path = folder / "plan.md"
    if not plan_path.is_file() or not plan_path.read_text(encoding="utf-8").strip():
        plan_path.write_text(plan_md or SAMPLE_PLAN, encoding="utf-8")

    # From here on, only production HTTP routes touch the session (dual-write ON).
    os.environ["AGENT_LAB_MISSION_DUAL_WRITE"] = "1"
    client = _client(sessions_root)
    approve_response = client.post(f"/api/sessions/{session_id}/plan/approve", json={"goal": topic})
    approve_body = approve_response.json()
    read_model_after_approve = _read_model(client, session_id)

    result: dict[str, Any] = {
        "session_id": session_id,
        "topic": topic,
        "room_run": {
            "turns_recorded": len(turns),
            "agent_messages": agent_message_count,
            "peer_review_rounds_called": peer_calls["n"],
            "plan_md_chars": len(plan_md or ""),
            "plan_workflow_phase_after_room_run": pw_phase_before,
        },
        "plan_approve_route": {
            "status_code": approve_response.status_code,
            "mirrored": approve_body.get("mission_dual_write", {}).get("mirrored"),
            "plan_workflow_phase": approve_body.get("plan_workflow", {}).get("phase"),
        },
        "read_model_after_approve": {
            "migrated": read_model_after_approve.get("migrated"),
            "state": read_model_after_approve.get("state"),
        },
    }

    # Best-effort: also drive execute/resolve via the real route if the
    # Room-synthesized plan yields a dry-runnable action. Not required for
    # the dogfood evidence to be valid (plan/approve alone is real Room
    # traffic through a production route) but adds coverage when possible.
    execute_result: dict[str, Any] = {"attempted": False}
    try:
        from agent_lab.plan.execute_worktree import create_exec_worktree
        from agent_lab.run.meta import patch_run_meta
        import subprocess

        workspace = Path(tempfile.mkdtemp(prefix="dualwrite-room-dogfood-repo-"))

        def _git(cwd: Path, *args: str) -> str:
            r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
            return r.stdout.strip()

        _git(workspace.parent, "--version")  # sanity: git available
        workspace.mkdir(exist_ok=True)
        _git(workspace, "init", "-b", "main")
        (workspace / "src").mkdir()
        (workspace / "src" / "dogfood_marker.py").write_text("v1\n", encoding="utf-8")
        _git(workspace, "add", ".")
        _git(workspace, "commit", "-m", "init")

        exec_id = f"exec-{session_id}"
        ew = create_exec_worktree(folder, exec_id=exec_id, git_root=workspace, action_key="now:1", session_id=session_id)
        (ew.worktree_path / "src" / "dogfood_marker.py").write_text("v2 room dogfood\n", encoding="utf-8")
        _git(ew.worktree_path, "add", "-A")
        _git(ew.worktree_path, "commit", "-m", "room dogfood change")
        row = {
            "id": exec_id,
            "status": "pending_approval",
            "isolation_effective": "worktree",
            "action_index": 1,
            "action_kind": "now",
            "action_what": "implement dogfood marker",
            "action_where": "`src/dogfood_marker.py`",
            "action_verify": "`pytest tests/test_dogfood_marker.py`",
            "paths_outside_expected": [],
            **ew.to_dict(),
        }

        def _seed(run: dict[str, Any]) -> dict[str, Any]:
            run["executions"] = [row]
            return run

        patch_run_meta(folder, _seed)
        resolve_response = client.post(
            f"/api/sessions/{session_id}/execute/resolve",
            json={"execution_id": exec_id, "vote": "approve"},
        )
        resolve_body = resolve_response.json()
        read_model_after_execute = _read_model(client, session_id)
        execute_result = {
            "attempted": True,
            "status_code": resolve_response.status_code,
            "mirrored": resolve_body.get("mission_dual_write", {}).get("mirrored"),
            "execution_status": (resolve_body.get("execution") or {}).get("status"),
            "read_model_state": read_model_after_execute.get("state"),
        }
    except Exception as exc:  # pragma: no cover — best-effort extension only
        execute_result = {"attempted": True, "error": str(exc)[:300]}

    result["execute_resolve_route"] = execute_result
    return result


def run_dogfood(sessions_root: Path, topics: list[str]) -> dict[str, Any]:
    sessions_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
    os.environ.setdefault("AGENT_LAB_TURN_POLICY", "1")
    os.environ.setdefault("AGENT_LAB_CLARIFIER", "0")
    os.environ.setdefault("AGENT_LAB_PLAN_FSM_SKILL_FIRST", "0")
    os.environ.setdefault("AGENT_LAB_ROOM_PRESET", "supervisor")

    tests_dir = ROOT / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    from agent_mocks import disable_execute_inbox_mcp
    import pytest

    monkeypatch = pytest.MonkeyPatch()
    disable_execute_inbox_mcp(monkeypatch)

    sessions: list[dict[str, Any]] = []
    try:
        with _isolated_config_dir():
            for topic in topics:
                sessions.append(_run_one_dogfood_session(sessions_root, topic))
    finally:
        monkeypatch.undo()

    dogfood_pass = all(
        s["plan_approve_route"]["status_code"] == 200
        and s["plan_approve_route"]["mirrored"] is True
        and s["read_model_after_approve"]["migrated"] is True
        for s in sessions
    )
    return {
        "sessions_root": str(sessions_root),
        "session_count": len(sessions),
        "dogfood_pass": dogfood_pass,
        "sessions": sessions,
        "created_session_dirs": [s["session_id"] for s in sessions],
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument(
        "--topics",
        nargs="+",
        default=[
            "dual-write dogfood: 세션 A — plan approve 실사용 흐름 확인",
            "dual-write dogfood: 세션 B — execute route 실사용 흐름 확인",
        ],
    )
    args = parser.parse_args()
    report = run_dogfood(args.sessions, args.topics)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["dogfood_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
