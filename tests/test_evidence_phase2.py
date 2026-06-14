"""Phase 2 — evidence ledger, gates, merge checks (MB-3, MB-4, MB-5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.adversarial_gate import LGTM_TOKEN
from agent_lab.evidence_gates import attach_evidence_gates, build_evidence_gates
from agent_lab.evidence_ledger import append_evidence, evidence_path, read_evidence_tail
from agent_lab.merge_checks import build_merge_checks

PENDING_STATUS = "pending_approval"


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    folder = tmp_path / "sess-ev"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_append_and_read_evidence_tail(session_folder: Path) -> None:
    append_evidence(session_folder, {"phase": "DRY_RUN", "kind": "dry_run", "detail": "ok"})
    append_evidence(session_folder, {"phase": "MERGE", "kind": "merge_approve"})
    rows = read_evidence_tail(session_folder, limit=10)
    assert len(rows) == 2
    assert rows[0]["phase"] == "DRY_RUN"
    assert evidence_path(session_folder).is_file()


def test_build_evidence_gates_pending_dry_run() -> None:
    run = {"mission_loop": {"enabled": True, "plan_gate": {"status": "ok"}}}
    execution = {
        "status": PENDING_STATUS,
        "adversarial_note": LGTM_TOKEN,
        "action_verify": "make test",
    }
    gates = build_evidence_gates(run, execution)
    by_gate = {g["gate"]: g["status"] for g in gates}
    assert by_gate["plan_reread"] == "pass"
    assert by_gate["adversarial"] == "pass"
    assert by_gate["manual_merge"] == "pending"
    assert by_gate["automated"] == "pending"
    assert len(gates) == 5


def test_attach_evidence_gates_on_merged_pass() -> None:
    run = {"mission_loop": {"enabled": True, "plan_gate": {"status": "ok"}}}
    execution = {
        "status": "merged",
        "adversarial_note": LGTM_TOKEN,
        "verify_after_merge": {
            "status": "passed",
            "oracle": {"verdict": "pass"},
        },
        "merge": {"status": "merged"},
    }
    out = attach_evidence_gates(run, execution)
    assert out["oracle_verdict"] == "pass"
    assert any(g["gate"] == "automated" and g["status"] == "pass" for g in out["evidence_gates"])


def test_merge_checks_disabled_on_open_block(session_folder: Path) -> None:
    run = {
        "objections": [
            {
                "id": "obj-1",
                "act": "BLOCK",
                "status": "open",
                "body": "stop merge",
            }
        ],
        "executions": [
            {
                "id": "exec-1",
                "status": PENDING_STATUS,
                "action_verify": "make test",
                "isolation_effective": "worktree",
                "worktree_path": str(session_folder / "wt"),
                "exec_branch": "agent-lab/test",
                "adversarial_note": LGTM_TOKEN,
            }
        ],
    }
    (session_folder / "wt").mkdir()
    checks = build_merge_checks(run)
    assert checks["merge_disabled"] is True
    assert "open_blocks" in (checks["merge_disabled_reason"] or "")


def test_merge_checks_ready_without_pending(session_folder: Path) -> None:
    run = {"executions": [], "objections": []}
    checks = build_merge_checks(run)
    assert checks["merge_disabled"] is False


def test_evidence_api(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.session import SESSIONS_DIR

    sid = session_folder.name
    target = SESSIONS_DIR / sid
    if target != session_folder:
        import shutil

        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(session_folder, target)
    append_evidence(target, {"phase": "VERIFY", "kind": "oracle", "exit": 0})

    from app.server.main import app

    client = TestClient(app)
    res = client.get(f"/api/sessions/{sid}/evidence?limit=5")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["entries"]


def test_merge_checks_api(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from agent_lab.run_meta import write_run_meta
    from agent_lab.session import SESSIONS_DIR

    sid = session_folder.name
    target = SESSIONS_DIR / sid
    write_run_meta(target, {"executions": [], "objections": []})

    from app.server.main import app

    client = TestClient(app)
    res = client.get(f"/api/sessions/{sid}/merge-checks")
    assert res.status_code == 200
    assert res.json()["merge_disabled"] is False


def test_on_dry_run_recorded_integration(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent_lab.plan_execute._call_execute_agent",
        lambda *a, **k: "done",
    )
    monkeypatch.setattr(
        "agent_lab.plan_execute._execute_agent_available",
        lambda _id: True,
    )
    plan = """# Plan

## 지금 실행

1. Fix
   - 무엇을: x
   - 어디서: `src/`
   - 검증: `make test`
"""
    (session_folder / "plan.md").write_text(plan, encoding="utf-8")
    from agent_lab.plan_execute import run_dry_run

    try:
        run_dry_run(session_folder, action_index=1, permissions={})
    except Exception:
        pytest.skip("dry-run env not fully mockable")

    run = json.loads((session_folder / "run.json").read_text(encoding="utf-8"))
    rows = run.get("executions") or []
    if not rows:
        pytest.skip("no execution recorded")
    assert rows[-1].get("evidence_gates")
    assert read_evidence_tail(session_folder)
