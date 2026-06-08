from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.context_bundle import build_context_bundle
from agent_lab.context_layers import (
    get_context_layers,
    mission_wisdom_layer_enabled,
    patch_context_layers,
    repo_tree_layer_enabled,
    should_use_mission_slim_bundle,
)
from agent_lab.mission_loop import append_wisdom_note, build_mission_wisdom_block, enable_mission_loop
from agent_lab.run_meta import read_run_meta


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    folder = tmp_path / "sess-ctx"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_patch_context_layers(session_folder: Path) -> None:
    out = patch_context_layers(session_folder, {"mission_wisdom": False})
    assert out["mission_wisdom"] is False
    assert out["repo_tree"] is True
    run = read_run_meta(session_folder)
    assert get_context_layers(run)["mission_wisdom"] is False


def test_mission_wisdom_block_respects_layer_toggle(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    append_wisdom_note(session_folder, line="remember this")
    patch_context_layers(session_folder, {"mission_wisdom": False})
    run = read_run_meta(session_folder)
    run["_session_id"] = session_folder.name
    run["mission_loop"]["phase"] = "DISCUSS"
    assert build_mission_wisdom_block(run) == ""


def test_context_layers_api(session_folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.server.main import app

    monkeypatch.setattr(
        "app.server.routers.context_layers.session_folder_or_404",
        lambda _sid: session_folder,
    )
    client = TestClient(app)
    get_res = client.get("/api/sessions/sess-ctx/context-layers")
    assert get_res.status_code == 200
    assert get_res.json()["context_layers"]["mission_wisdom"] is True

    patch_res = client.patch(
        "/api/sessions/sess-ctx/context-layers",
        json={"mission_wisdom": False},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["context_layers"]["mission_wisdom"] is False
    assert mission_wisdom_layer_enabled(read_run_meta(session_folder)) is False


def test_should_use_mission_slim_bundle(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    run = read_run_meta(session_folder)
    run["mission_loop"]["phase"] = "DISCUSS"
    assert should_use_mission_slim_bundle(run) is True
    run["mission_loop"]["phase"] = "EXECUTE_QUEUE"
    assert should_use_mission_slim_bundle(run) is False


def test_mission_slim_forces_efficiency_bundle(session_folder: Path) -> None:
    enable_mission_loop(session_folder)
    run = read_run_meta(session_folder)
    run["mission_loop"]["phase"] = "PLAN_GATE"
    bundle = build_context_bundle("t", [], "claude", run_meta=run)
    assert bundle.meta.slim_context is True
    assert bundle.meta.efficiency_mode is True


def test_repo_tree_layer_toggle(session_folder: Path) -> None:
    patch_context_layers(session_folder, {"repo_tree": False})
    run = read_run_meta(session_folder)
    assert repo_tree_layer_enabled(run) is False
