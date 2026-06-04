"""PROJECT.md bootstrap (init-project-memory)."""

from __future__ import annotations

from pathlib import Path

from agent_lab.project_memory import PROJECT_MD_CAP, bootstrap_project_md, project_md_path
from agent_lab.session_guidance import build_session_guidance_block


def test_bootstrap_creates_project_md(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n\nA sample project for tests.\n")
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n")
    text = bootstrap_project_md(tmp_path)
    path = project_md_path(tmp_path)
    assert path.is_file()
    assert "프로젝트 메모리" in text
    assert "A sample project" in text
    assert len(text) <= PROJECT_MD_CAP


def test_bootstrap_skips_existing_without_overwrite(tmp_path: Path):
    agent_lab = tmp_path / ".agent-lab"
    agent_lab.mkdir()
    existing = agent_lab / "PROJECT.md"
    existing.write_text("# keep\n")
    out = bootstrap_project_md(tmp_path)
    assert out == "# keep\n"
    assert existing.read_text(encoding="utf-8") == "# keep\n"


def test_bootstrap_injected_in_session_guidance(tmp_path: Path):
    bootstrap_project_md(tmp_path, overwrite=True)
    block = build_session_guidance_block(
        {
            "workspace_binding": {"path": str(tmp_path), "label": "demo"},
        }
    )
    assert "PROJECT.md" in block
    assert "프로젝트 메모리" in block


def test_init_project_memory_cli_dry_run(tmp_path: Path):
    import subprocess
    import sys

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndescription = "CLI dry run"\n'
    )
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts/init_project_memory.py"), str(tmp_path), "--dry-run"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "CLI dry run" in proc.stdout
    assert not project_md_path(tmp_path).is_file()
