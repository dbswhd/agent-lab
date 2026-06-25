"""P3 edit-time syntax gate (AGENT_LAB_SYNTAX_GATE, default off).

Covers AC1-AC6 + defensive-path + deterministic ordering (Critic N2).
"""

from __future__ import annotations

from pathlib import Path

from agent_lab import merge_checks
from agent_lab import syntax_gate as sg


def _execution(worktree: Path, *paths: str) -> dict:
    return {
        "id": "exec-1",
        "isolation_effective": "worktree",
        "worktree_path": str(worktree),
        "exec_branch": "exec/x",
        "exec_commit_sha": "deadbeef",
        "action_verify": "run pytest -q",
        "source_touched_paths": list(paths),
    }


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# --- helper level -----------------------------------------------------------


def test_ac1_broken_py_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SYNTAX_GATE", "1")
    _write(tmp_path, "bad.py", "def f(:\n    pass\n")
    ex = _execution(tmp_path, "bad.py")
    res = sg.evaluate_syntax_gate(ex)
    assert res["id"] == "syntax_gate"
    assert res["ok"] is False
    assert res["detail"].startswith("bad.py:")


def test_ac2_valid_py_ok(tmp_path):
    _write(tmp_path, "good.py", "def f():\n    return 1\n")
    res = sg.evaluate_syntax_gate(_execution(tmp_path, "good.py"))
    assert res["ok"] is True


def test_ac3_non_py_skipped(tmp_path):
    _write(tmp_path, "data.txt", "def f(: not python")
    res = sg.evaluate_syntax_gate(_execution(tmp_path, "data.txt"))
    assert res["ok"] is True
    assert "no changed .py" in res["detail"]


def test_ac4_no_pending_ok():
    assert sg.evaluate_syntax_gate(None)["ok"] is True


def test_defensive_missing_unreadable_outside(tmp_path):
    # missing file referenced + a path escaping the worktree -> skipped, ok:True
    ex = _execution(tmp_path, "missing.py", "../escape.py")
    res = sg.evaluate_syntax_gate(ex)
    assert res["ok"] is True


def test_ac_n2_deterministic_first_error(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SYNTAX_GATE", "1")
    _write(tmp_path, "a_bad.py", "def a(:\n")
    _write(tmp_path, "z_bad.py", "def z(:\n")
    ex = _execution(tmp_path, "z_bad.py", "a_bad.py")
    r1 = sg.evaluate_syntax_gate(ex)
    r2 = sg.evaluate_syntax_gate(ex)
    assert r1 == r2  # deterministic
    # changed_python_files sorts -> a_bad.py reported first regardless of input order
    assert r1["detail"].startswith("a_bad.py:")


def test_changed_python_files_dedup_and_inside(tmp_path):
    _write(tmp_path, "x.py", "x=1\n")
    ex = _execution(tmp_path, "x.py", "x.py", "../outside.py", "note.md")
    files = sg.changed_python_files(ex)
    assert len(files) == 1
    assert files[0].name == "x.py"


# --- merge_checks integration ----------------------------------------------


def test_ac5_flag_off_gate_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SYNTAX_GATE", "0")
    _write(tmp_path, "bad.py", "def f(:\n")
    run = {"executions": [{**_execution(tmp_path, "bad.py"), "status": "pending_approval"}]}
    payload = merge_checks.build_merge_checks(run)
    ids = [c["id"] for c in payload["checks"]]
    assert "syntax_gate" not in ids  # opt-out via =0: gate absent, not ok:True


def test_ac1_flag_on_gate_blocks_merge(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SYNTAX_GATE", "1")
    _write(tmp_path, "bad.py", "def f(:\n")
    run = {"executions": [{**_execution(tmp_path, "bad.py"), "status": "pending_approval"}]}
    payload = merge_checks.build_merge_checks(run)
    ids = [c["id"] for c in payload["checks"]]
    assert "syntax_gate" in ids
    assert payload["merge_disabled"] is True
    assert "syntax_gate" in (payload["merge_disabled_reason"] or "")


def test_flag_on_valid_does_not_block(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_SYNTAX_GATE", "1")
    _write(tmp_path, "good.py", "ok = True\n")
    run = {"executions": [{**_execution(tmp_path, "good.py"), "status": "pending_approval"}]}
    payload = merge_checks.build_merge_checks(run)
    gate = [c for c in payload["checks"] if c["id"] == "syntax_gate"][0]
    assert gate["ok"] is True


def test_enabled_helper(monkeypatch):
    # default ON: absent/empty => enabled; opt-out via =0
    monkeypatch.delenv("AGENT_LAB_SYNTAX_GATE", raising=False)
    assert sg.syntax_gate_enabled() is True
    monkeypatch.setenv("AGENT_LAB_SYNTAX_GATE", "0")
    assert sg.syntax_gate_enabled() is False
    monkeypatch.setenv("AGENT_LAB_SYNTAX_GATE", "on")
    assert sg.syntax_gate_enabled() is True
