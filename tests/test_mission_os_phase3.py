"""Mission OS Phase 3 — trust_budget, merge_classifier, auto-merge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_lab.auto_merge import evaluate_auto_merge_eligibility, resolve_auto_merge
from agent_lab.gateway.telegram_adapter import handle_gateway_command
from agent_lab.merge_classifier import classify_source_paths
from agent_lab.run_meta import read_run_meta
from agent_lab.trust_budget import consume_auto_merge_budget, get_trust_budget, set_trust_budget
from app.server.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    folder = tmp_path / "auto-merge-sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("auto\n", encoding="utf-8")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    return folder


def _write_run(folder: Path, payload: dict) -> None:
    (folder / "run.json").write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def _eligible_pending(**overrides: object) -> dict:
    row = {
        "id": "exec-docs",
        "status": "pending_approval",
        "isolation_effective": "apply",
        "action_verify": "make test",
        "source_touched_paths": ["docs/README.md"],
    }
    row.update(overrides)
    return row


def test_classifier_docs_only_and_deny() -> None:
    assert classify_source_paths(["docs/README.md"]) == "docs_only"
    assert classify_source_paths(["tests/test_foo.py"]) == "test_only"
    assert classify_source_paths(["src/agent_lab/foo.py"]) == "single_file"
    assert classify_source_paths(["pyproject.toml"]) is None
    assert classify_source_paths(["docs/a.md", "src/b.py"]) is None


def test_trust_budget_defaults_and_patch(session_folder: Path) -> None:
    _write_run(session_folder, {"gate_profile": "dev"})
    assert get_trust_budget(read_run_meta(session_folder))["auto_merge_remaining"] == 0

    _write_run(session_folder, {"gate_profile": "assistant"})
    budget = get_trust_budget(read_run_meta(session_folder))
    assert budget["auto_merge_remaining"] == 0
    assert "docs_only" in budget["classifier_allow"]

    updated = set_trust_budget(session_folder, {"auto_merge_remaining": 3, "auto_merge_total": 5})
    assert updated["auto_merge_remaining"] == 3
    assert updated["auto_merge_total"] == 5


def test_consume_trust_budget(session_folder: Path) -> None:
    set_trust_budget(session_folder, {"auto_merge_remaining": 1})
    before, after = consume_auto_merge_budget(session_folder)
    assert before == 1 and after == 0
    with pytest.raises(ValueError, match="exhausted"):
        consume_auto_merge_budget(session_folder)


def test_dev_profile_blocks_auto_merge(session_folder: Path) -> None:
    _write_run(
        session_folder,
        {
            "gate_profile": "dev",
            "trust_budget": {"auto_merge_remaining": 5},
            "executions": [_eligible_pending()],
        },
    )
    elig = evaluate_auto_merge_eligibility(session_folder)
    assert elig["eligible"] is False
    assert elig["reason"] == "dev_profile_requires_human_merge"


def test_assistant_eligible_docs_merge(session_folder: Path) -> None:
    _write_run(
        session_folder,
        {
            "gate_profile": "assistant",
            "trust_budget": {
                "auto_merge_remaining": 2,
                "auto_merge_total": 2,
                "classifier_allow": ["docs_only"],
            },
            "executions": [_eligible_pending()],
        },
    )
    elig = evaluate_auto_merge_eligibility(session_folder)
    assert elig["eligible"] is True
    assert elig["classifier"] == "docs_only"


def test_classifier_denied_blocks(session_folder: Path) -> None:
    _write_run(
        session_folder,
        {
            "gate_profile": "assistant",
            "trust_budget": {"auto_merge_remaining": 2},
            "executions": [
                _eligible_pending(source_touched_paths=["pyproject.toml", "docs/a.md"]),
            ],
        },
    )
    elig = evaluate_auto_merge_eligibility(session_folder)
    assert elig["eligible"] is False
    assert elig["reason"] == "classifier_denied"


def test_auto_merge_api_eligibility_and_patch(
    client: TestClient,
    session_folder: Path,
) -> None:
    sid = session_folder.name
    _write_run(
        session_folder,
        {
            "gate_profile": "assistant",
            "trust_budget": {"auto_merge_remaining": 0},
            "executions": [_eligible_pending()],
        },
    )
    r = client.get(f"/api/sessions/{sid}/auto-merge/eligibility")
    assert r.status_code == 200
    assert r.json()["eligible"] is False

    r = client.patch(
        f"/api/sessions/{sid}/trust-budget",
        json={"auto_merge_remaining": 1, "classifier_allow": ["docs_only"]},
    )
    assert r.status_code == 200
    assert r.json()["trust_budget"]["auto_merge_remaining"] == 1

    r = client.get(f"/api/sessions/{sid}/auto-merge/eligibility")
    assert r.status_code == 200
    assert r.json()["eligible"] is True


def test_resolve_auto_merge_records_audit(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_run(
        session_folder,
        {
            "gate_profile": "assistant",
            "trust_budget": {"auto_merge_remaining": 1, "classifier_allow": ["docs_only"]},
            "executions": [_eligible_pending()],
        },
    )

    def _fake_resolve(folder, *, execution_id, vote, permissions=None, approved_by="human", auto_merge_meta=None):
        from agent_lab.run_meta import patch_run_meta

        def _mark(run):
            for row in run.get("executions") or []:
                if row.get("id") == execution_id:
                    row["status"] = "merged"
            return run

        patch_run_meta(folder, _mark)
        approval = {
            "id": "appr-test",
            "execution_id": execution_id,
            "vote": vote,
            "by": approved_by,
            "auto_merge": True,
            **(auto_merge_meta or {}),
        }
        if approved_by == "auto":
            before, after = consume_auto_merge_budget(folder)
            approval["budget_before"] = before
            approval["budget_after"] = after
        return {
            "ok": True,
            "execution": {"id": execution_id, "status": "merged"},
            "approval": approval,
        }

    monkeypatch.setattr("agent_lab.plan_execute.resolve_execution", _fake_resolve)

    result = resolve_auto_merge(session_folder, execution_id="exec-docs")
    assert result["auto_merge"]["budget_before"] == 1
    assert result["auto_merge"]["budget_after"] == 0
    assert get_trust_budget(read_run_meta(session_folder))["auto_merge_remaining"] == 0


def test_telegram_approve_merge_pending_apply(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_run(
        session_folder,
        {
            "gate_profile": "assistant",
            "executions": [_eligible_pending()],
        },
    )

    def _resolve(folder, *, execution_id, vote, permissions=None, approved_by="human", auto_merge_meta=None):
        return {"execution": {"id": execution_id, "status": "completed"}}

    monkeypatch.setattr("agent_lab.plan_execute.resolve_execution", _resolve)
    result = handle_gateway_command(
        session_id=session_folder.name,
        text="/approve merge",
        gate_profile="assistant",
    )
    assert result["ok"] is True
    assert "merge approved" in result["reply"]


def test_telegram_approve_auto_blocked_on_dev(session_folder: Path) -> None:
    _write_run(
        session_folder,
        {
            "gate_profile": "dev",
            "executions": [_eligible_pending()],
        },
    )
    result = handle_gateway_command(
        session_id=session_folder.name,
        text="/approve auto",
        gate_profile="dev",
    )
    assert result["ok"] is False
    assert "blocked" in result["reply"]
