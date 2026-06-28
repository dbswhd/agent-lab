"""Track 2.0b — syntax_gate_core seam tests."""

from __future__ import annotations

from pathlib import Path

from agent_lab.syntax_gate_core import merge_result_for_syntax_scan, scan_python_syntax


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_scan_python_syntax_first_error(tmp_path: Path) -> None:
    _write(tmp_path, "a_bad.py", "def a(:\n")
    _write(tmp_path, "z_bad.py", "def z(:\n")
    paths = sorted(tmp_path.glob("*.py"))
    hit = scan_python_syntax(paths, root=tmp_path)
    assert hit is not None
    assert hit[0] == "a_bad.py"


def test_merge_result_for_syntax_scan_ok(tmp_path: Path) -> None:
    _write(tmp_path, "good.py", "x = 1\n")
    paths = [tmp_path / "good.py"]
    res = merge_result_for_syntax_scan(paths, scan_python_syntax(paths, root=tmp_path))
    assert res["ok"] is True
    assert "1 .py ok" in res["detail"]


def test_merge_result_empty_paths() -> None:
    assert merge_result_for_syntax_scan([], None)["detail"] == "no changed .py"
