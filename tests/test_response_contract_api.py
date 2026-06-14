from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_lab.reply_policy import build_guidance_parts, resolve_reply_policy
from agent_lab.run_meta import read_run_meta


def _session(sessions_dir: Path) -> Path:
    folder = sessions_dir / "contract-api"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "topic": "contract api",
                "agents": ["codex"],
                "status": "completed",
                "turns": [],
                "actions": [],
                "approvals": [],
                "executions": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return folder


def test_response_contract_patch_records_preset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Given: a persisted room session.
    sessions_dir = tmp_path / "sessions"
    folder = _session(sessions_dir)
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    from app.server.main import app

    # When: Human selects a response contract preset.
    response = TestClient(app).patch(
        "/api/sessions/contract-api/response-contract",
        json={"preset": "evidence_first"},
    )

    # Then: the API returns and persists the preset contract.
    assert response.status_code == 200
    body = response.json()
    assert body["response_contract"]["preset"] == "evidence_first"
    assert body["response_contract"]["label"] == "Evidence-first"
    assert "evidence" in body["response_contract"]["guidance"].lower()
    saved = read_run_meta(folder)
    assert saved["response_contract"]["preset"] == "evidence_first"


def test_response_contract_guidance_is_injected_when_present() -> None:
    # Given: a session run meta with a selected response contract.
    run_meta = {"response_contract": {"preset": "plan_ready"}}
    policy = resolve_reply_policy(turn_profile="analyze")

    # When: the room builds guidance parts for an agent payload.
    parts = build_guidance_parts(policy, run_meta=run_meta, agent="codex")

    # Then: the preset guidance is included before the normal guidance stack.
    assert parts[0].startswith("[Response contract · Plan-ready]")
    assert "## 지금 실행" in parts[0]


def test_response_contract_patch_rejects_unknown_preset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Given: a persisted room session.
    sessions_dir = tmp_path / "sessions"
    _session(sessions_dir)
    monkeypatch.setattr("app.server.deps.SESSIONS_DIR", sessions_dir)
    from app.server.main import app

    # When: an unknown preset is submitted.
    response = TestClient(app).patch(
        "/api/sessions/contract-api/response-contract",
        json={"preset": "verbose"},
    )

    # Then: FastAPI rejects it at the boundary.
    assert response.status_code == 422
