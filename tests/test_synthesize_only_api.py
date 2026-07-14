"""synthesize_only is TurnPolicy Human override — not mode/synthesize."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import agent_lab.session as session_mod
    import app.server.deps as deps_mod

    # /api/room/runs drives _run_with_lock() -> try_begin_run(), which holds
    # a real cross-process fcntl lock at config_dir()/run.lock. Without a
    # private dir per test, concurrent xdist workers race on the same
    # shared machine-wide lock file: try_begin_run() spuriously returns
    # False, the lock-blocked branch fires without ever calling run_body(),
    # and the mocked synthesize_session_plan never runs (KeyError: 'folder'
    # on the `called` dict — see tests/test_run_control.py's
    # _isolate_run_lock for the full story).
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(tmp_path / ".agent-lab-config"))
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(deps_mod, "SESSIONS_DIR", tmp_path)
    folder = tmp_path / "sess-synth"
    folder.mkdir()
    (folder / "topic.txt").write_text("hello\n", encoding="utf-8")
    (folder / "run.json").write_text("{}\n", encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        json.dumps({"role": "user", "content": "hi"}) + "\n",
        encoding="utf-8",
    )

    from app.server.main import app

    return TestClient(app), folder


def test_synthesize_only_requires_session_id(client) -> None:
    api, _folder = client
    res = api.post(
        "/api/room/runs",
        data={"synthesize_only": "true", "topic": "", "agents": "[]"},
    )
    assert res.status_code == 400
    assert "session_id" in res.json()["detail"]


def test_synthesize_only_ignores_mode_and_agents(client) -> None:
    api, folder = client
    called: dict[str, object] = {}

    def _fake_synth(folder_arg, **kwargs):
        called["folder"] = folder_arg
        called["kwargs"] = kwargs
        return "# plan\n", "summary"

    with patch("app.server.routers.room.synthesize_session_plan", _fake_synth):
        with api.stream(
            "POST",
            "/api/room/runs",
            data={
                "synthesize_only": "true",
                "session_id": folder.name,
                # Deprecated fields — must not block or change path.
                "mode": "plan",
                "synthesize": "true",
                "topic": "",
                "agents": "[]",
                "turn_profile": "loop",
            },
        ) as res:
            assert res.status_code == 200
            body = "".join(res.iter_text())

    assert "room.synthesize_only" in body
    assert '"synthesize_only": true' in body or '"synthesize_only":true' in body
    assert called["folder"] == folder


def test_normal_run_still_requires_topic(client) -> None:
    api, _folder = client
    res = api.post(
        "/api/room/runs",
        data={"topic": "", "agents": '["cursor"]', "synthesize_only": "false"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "topic required"
