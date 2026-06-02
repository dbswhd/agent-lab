"""Unified workspace roots for room agents."""

from __future__ import annotations

from agent_lab.workspace_roots import (
    discuss_primary_workspace,
    execute_workspace_info,
    lecture_script_root,
    pipeline_root,
    primary_workspace,
    resolve_execute_workspace,
    resolve_workspace_roots,
    workspace_label,
    workspace_roots_block,
)


def test_default_root_is_agent_lab():
    roots = resolve_workspace_roots(None)
    assert len(roots) >= 1
    assert primary_workspace(None) == roots[0]


def test_pipeline_root_when_enabled(tmp_path, monkeypatch):
    pipeline = tmp_path / "quant-pipeline"
    pipeline.mkdir()
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    perms = {
        "cursor": {"local_pipeline": True},
        "claude": {"local_pipeline": True},
    }
    roots = resolve_workspace_roots(perms)
    assert pipeline.resolve() in roots


def test_lecture_script_root_when_enabled(tmp_path, monkeypatch):
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))
    perms = {
        "cursor": {"local_lecture_script": True},
        "claude": {"local_lecture_script": True},
    }
    roots = resolve_workspace_roots(perms)
    assert lecture.resolve() in roots


def test_workspace_roots_block_lists_paths():
    block = workspace_roots_block(None)
    assert "Workspace roots" in block
    assert "agent-lab" in block.lower() or "/" in block


def test_resolve_execute_workspace_picks_lecture_script_when_files_exist(
    tmp_path, monkeypatch
):
    agent_lab = tmp_path / "agent-lab"
    agent_lab.mkdir()
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()
    (lecture / "extract_lecturenote.py").write_text("# script\n", encoding="utf-8")
    (lecture / "lecturenote_exercises.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setenv("AGENT_LAB_ROOT", str(agent_lab))
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))

    expected = ["extract_lecturenote.py", "lecturenote_exercises.json"]
    cwd, perms = resolve_execute_workspace({}, expected)

    assert cwd == lecture.resolve()
    assert perms["cursor"]["local_lecture_script"] is True


def test_resolve_execute_workspace_stays_agent_lab_when_files_only_there(
    tmp_path, monkeypatch
):
    agent_lab = tmp_path / "agent-lab"
    agent_lab.mkdir()
    (agent_lab / "plan_execute.py").write_text("# local\n", encoding="utf-8")
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()

    monkeypatch.setenv("AGENT_LAB_ROOT", str(agent_lab))
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))

    cwd, _ = resolve_execute_workspace({}, ["plan_execute.py"])
    assert cwd == agent_lab.resolve()


def test_resolve_execute_workspace_heuristic_for_lecture_basenames(
    tmp_path, monkeypatch
):
    agent_lab = tmp_path / "agent-lab"
    agent_lab.mkdir()
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()

    monkeypatch.setenv("AGENT_LAB_ROOT", str(agent_lab))
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))

    cwd, perms = resolve_execute_workspace({}, ["extract_lecturenote.py"])
    assert cwd == lecture.resolve()
    assert perms["cursor"]["local_lecture_script"] is True


def test_normalize_expected_paths_filters_non_file_tokens(tmp_path, monkeypatch):
    agent_lab = tmp_path / "agent-lab"
    agent_lab.mkdir()
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()
    target = lecture / "build.mjs"
    target.write_text("// build\n", encoding="utf-8")

    monkeypatch.setenv("AGENT_LAB_ROOT", str(agent_lab))
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))

    raw = [
        str(target),
        "page.evaluate",
        "9.2→9.3",
    ]
    cwd, _ = resolve_execute_workspace({}, raw)
    assert cwd == lecture.resolve()
    info = execute_workspace_info({}, raw)
    assert info["paths_found"] == ["build.mjs"]
    assert info["paths_missing"] == []


def test_resolve_execute_workspace_absolute_path_hint(tmp_path, monkeypatch):
    agent_lab = tmp_path / "agent-lab"
    agent_lab.mkdir()
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()
    target = lecture / "build.mjs"
    target.write_text("// build\n", encoding="utf-8")

    monkeypatch.setenv("AGENT_LAB_ROOT", str(agent_lab))
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))

    cwd, perms = resolve_execute_workspace({}, [str(target)])
    assert cwd == lecture.resolve()
    assert perms["cursor"]["local_lecture_script"] is True


def test_resolve_execute_workspace_absolute_path_to_new_file(tmp_path, monkeypatch):
    agent_lab = tmp_path / "agent-lab"
    agent_lab.mkdir()
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()
    target = lecture / "RECIPE.md"

    monkeypatch.setenv("AGENT_LAB_ROOT", str(agent_lab))
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))

    cwd, perms = resolve_execute_workspace({}, [str(target)])
    assert cwd == lecture.resolve()
    assert perms["cursor"]["local_lecture_script"] is True
    info = execute_workspace_info({}, [str(target)])
    assert info["label"] == "lecture-script"
    assert info["paths_found"] == []
    assert info["paths_missing"] == ["RECIPE.md"]


def test_workspace_label(tmp_path, monkeypatch):
    agent_lab = tmp_path / "agent-lab"
    agent_lab.mkdir()
    pipeline = tmp_path / "quant-pipeline"
    pipeline.mkdir()
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()
    monkeypatch.setenv("AGENT_LAB_ROOT", str(agent_lab))
    monkeypatch.setenv("QUANT_PIPELINE_ROOT", str(pipeline))
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))

    assert workspace_label(agent_lab) == "agent-lab"
    assert workspace_label(pipeline) == "quant-pipeline"
    assert workspace_label(lecture) == "lecture-script"
    assert pipeline_root() == pipeline.resolve()
    assert lecture_script_root() == lecture.resolve()


def test_discuss_primary_workspace_prefers_lecture_flag(tmp_path, monkeypatch):
    agent_lab = tmp_path / "agent-lab"
    agent_lab.mkdir()
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()
    monkeypatch.setenv("AGENT_LAB_ROOT", str(agent_lab))
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))
    perms = {"cursor": {"local_lecture_script": True}}
    assert discuss_primary_workspace(perms) == lecture.resolve()


def test_execute_workspace_info_paths_found(tmp_path, monkeypatch):
    agent_lab = tmp_path / "agent-lab"
    agent_lab.mkdir()
    lecture = tmp_path / "lecture-book"
    lecture.mkdir()
    (lecture / "target.py").write_text("# x\n", encoding="utf-8")

    monkeypatch.setenv("AGENT_LAB_ROOT", str(agent_lab))
    monkeypatch.setenv("LECTURE_SCRIPT_ROOT", str(lecture))

    info = execute_workspace_info({}, ["target.py", "missing.py"])
    assert info["label"] == "lecture-script"
    assert info["paths_found"] == ["target.py"]
    assert info["paths_missing"] == ["missing.py"]
