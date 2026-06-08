"""Tests for session start workspace + template binding."""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.session_setup import (
    CUSTOM_WORKSPACE_ID,
    build_setup_run_meta,
    list_session_templates,
    list_workspace_presets,
    merge_setup_permissions,
    resolve_custom_workspace,
    resolve_workspace_preset,
    resolve_workspace_selection,
    seed_session_setup,
    template_guidance_block,
)


def test_list_workspace_presets_includes_agent_lab():
    presets = list_workspace_presets()
    ids = {p["id"] for p in presets}
    assert "agent-lab" in ids
    agent_lab = next(p for p in presets if p["id"] == "agent-lab")
    assert agent_lab["available"] is True
    assert agent_lab["path"]


def test_list_session_templates():
    templates = list_session_templates()
    assert [t["id"] for t in templates] == ["general", "book-layout", "book-content"]


def test_merge_setup_permissions_sets_discuss_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_ROOT", str(tmp_path))
    perms = merge_setup_permissions({}, "agent-lab")
    assert perms["_discuss_cwd"] == str(tmp_path.resolve())
    assert perms["cursor"]["local_agent_lab"] is True
    assert perms["claude"]["local_agent_lab"] is True
    assert perms["codex"]["local_agent_lab"] is True


def test_build_setup_run_meta_book_content():
    meta = build_setup_run_meta(
        workspace_id="agent-lab",
        session_template="book-content",
    )
    assert meta["session_template"] == "book-content"
    assert meta["session_phase"] == "content"
    assert meta["layout_frozen"] is True
    assert meta["workspace_binding"]["preset"] == "agent-lab"


def test_seed_session_setup_writes_run_and_meta(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_ROOT", str(tmp_path))
    folder = tmp_path / "sessions" / "test-session"
    folder.mkdir(parents=True)
    (folder / "topic.txt").write_text("공수 교재\n", encoding="utf-8")

    seed_session_setup(
        folder,
        workspace_id="agent-lab",
        session_template="book-layout",
        topic="공수 교재",
    )

    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["workspace_preset"] == "agent-lab"
    assert run["session_template"] == "book-layout"
    assert run["session_phase"] == "layout"
    assert run["workspace_binding"]["path"] == str(tmp_path.resolve())

    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["session_template"] == "book-layout"
    assert meta["workspace_preset"] == "agent-lab"


def test_template_guidance_book_layout():
    block = template_guidance_block("book-layout")
    assert "Session template" in block
    assert "break-report" in block


def test_template_guidance_general_empty():
    assert template_guidance_block("general") == ""


def test_resolve_workspace_preset_missing_quant_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_lab.session_setup.pipeline_root",
        lambda: None,
    )
    assert resolve_workspace_preset("quant-pipeline") is None


def test_resolve_custom_workspace(tmp_path):
    custom = resolve_custom_workspace(str(tmp_path))
    assert custom is not None
    assert custom["id"] == CUSTOM_WORKSPACE_ID
    assert custom["path"] == str(tmp_path.resolve())


def test_merge_setup_permissions_custom_path(tmp_path):
    perms = merge_setup_permissions({}, CUSTOM_WORKSPACE_ID, str(tmp_path))
    assert perms["_discuss_cwd"] == str(tmp_path.resolve())
    assert perms["cursor"]["local_custom"] is True


def test_build_setup_run_meta_custom_path(tmp_path):
    meta = build_setup_run_meta(
        workspace_id=CUSTOM_WORKSPACE_ID,
        session_template="general",
        workspace_path=str(tmp_path),
    )
    assert meta["workspace_preset"] == CUSTOM_WORKSPACE_ID
    assert meta["session_template"] == "general"
    assert meta["workspace_binding"]["path"] == str(tmp_path.resolve())


def test_resolve_workspace_selection_requires_path_for_custom():
    try:
        resolve_workspace_selection(CUSTOM_WORKSPACE_ID, None)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "custom workspace path required" in str(e)


def test_resolve_workspace_selection_invalid_custom_path():
    try:
        resolve_workspace_selection(CUSTOM_WORKSPACE_ID, "/no/such/workspace")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "not found" in str(e)


def test_pipeline_root_falls_back_to_desktop_pipeline(tmp_path, monkeypatch):
    monkeypatch.delenv("QUANT_PIPELINE_ROOT", raising=False)
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text("[paths]\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(cfg_dir))
    desktop = tmp_path / "Desktop" / "pipeline"
    desktop.mkdir(parents=True)
    monkeypatch.setattr(
        "agent_lab.workspace_roots.Path.home",
        lambda: tmp_path,
    )
    from agent_lab.workspace_roots import pipeline_root

    assert pipeline_root() == desktop.resolve()
