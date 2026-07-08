"""HS4 REGRESS — regression_gate.py unit tests (mock-only + one real-git integration test)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from agent_lab.harness_proposer import load_candidate, propose_candidate, write_candidate
from agent_lab.regression_gate import (
    apply_diff,
    create_regression_worktree,
    diff_introduces_new_flags,
    diff_touches_manifest,
    eval_surface_gate_reason,
    held_in_scope,
    held_in_topics_for_tag,
    load_resolved_patterns,
    parse_diff_touched_files,
    record_resolved_pattern,
    regression_gate_enabled,
    remove_regression_worktree,
    run_regression_gate,
)


def test_regression_gate_enabled_default_off(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_REGRESSION_GATE", raising=False)
    assert regression_gate_enabled() is False
    monkeypatch.setenv("AGENT_LAB_REGRESSION_GATE", "1")
    assert regression_gate_enabled() is True


# ---------------------------------------------------------------------------
# HS4-2 — resolved_patterns.jsonl + held_in_scope
# ---------------------------------------------------------------------------


def test_held_in_topics_for_tag_weak_taste() -> None:
    assert held_in_topics_for_tag("weak_taste") == ["M3", "M4"]


def test_held_in_topics_for_tag_unknown_returns_empty() -> None:
    assert held_in_topics_for_tag("nonexistent_tag") == []


def test_record_and_load_resolved_patterns_append_only(tmp_path) -> None:
    record_resolved_pattern("fp:weak_taste:standard", candidate_id="pc-1", root=tmp_path)
    record_resolved_pattern("fp:weak_taste:standard", candidate_id="pc-2", root=tmp_path)
    rows = load_resolved_patterns(tmp_path)
    assert len(rows) == 2  # append-only — both rows present, no dedup at storage layer
    assert rows[0]["candidate_id"] == "pc-1"
    assert rows[1]["candidate_id"] == "pc-2"


def test_held_in_scope_own_pattern_only(tmp_path) -> None:
    candidate = {"pattern_id": "fp:weak_taste:standard"}
    scope = held_in_scope(candidate, root=tmp_path)
    assert scope["topics"] == ["M3", "M4"]
    assert scope["source_patterns"] == ["fp:weak_taste:standard"]


def test_held_in_scope_includes_resolved_patterns_cumulative(tmp_path) -> None:
    record_resolved_pattern("fp:weak_taste:quick", candidate_id="pc-1", root=tmp_path)
    candidate = {"pattern_id": "fp:harness_infra:standard"}
    scope = held_in_scope(candidate, root=tmp_path)
    # own tag (harness_infra) has no curated topics, but the resolved weak_taste
    # pattern's topics must still show up — the cumulative-set point of HS4-2.
    assert "M3" in scope["topics"]
    assert "fp:weak_taste:quick" in scope["source_patterns"]


# ---------------------------------------------------------------------------
# diff introspection
# ---------------------------------------------------------------------------

_SAMPLE_DIFF = """diff --git a/src/agent_lab/run/profile.py b/src/agent_lab/run/profile.py
--- a/src/agent_lab/run/profile.py
+++ b/src/agent_lab/run/profile.py
@@ -1,1 +1,2 @@
 x = 1
+y = 2
"""


def test_parse_diff_touched_files() -> None:
    assert parse_diff_touched_files(_SAMPLE_DIFF) == ["src/agent_lab/run/profile.py"]


def test_diff_introduces_new_flags_detects_unregistered_token() -> None:
    diff = "+++ b/x.py\n+FOO = os.getenv('AGENT_LAB_TOTALLY_NEW_FLAG')\n"
    assert "AGENT_LAB_TOTALLY_NEW_FLAG" in diff_introduces_new_flags(diff)


def test_diff_introduces_new_flags_ignores_registered_token() -> None:
    diff = "+++ b/x.py\n+FOO = os.getenv('AGENT_LAB_HARNESS_PROPOSER')\n"
    assert diff_introduces_new_flags(diff) == set()


def test_diff_introduces_new_flags_ignores_removed_lines() -> None:
    diff = "+++ b/x.py\n-FOO = os.getenv('AGENT_LAB_TOTALLY_NEW_FLAG')\n"
    assert diff_introduces_new_flags(diff) == set()


def test_diff_touches_manifest_true() -> None:
    diff = "+++ b/.agent-lab/harness/manifest.json\n+{}\n"
    assert diff_touches_manifest(diff) is True


def test_diff_touches_manifest_false() -> None:
    assert diff_touches_manifest(_SAMPLE_DIFF) is False


# ---------------------------------------------------------------------------
# HS4-6 — eval surface gate
# ---------------------------------------------------------------------------


def test_eval_surface_gate_reason_passes_with_eval_additions() -> None:
    candidate = {"eval_additions": ["M9"]}
    diff = "+++ b/.agent-lab/harness/manifest.json\n+{}\n"
    assert eval_surface_gate_reason(candidate, diff) is None


def test_eval_surface_gate_reason_rejects_manifest_touch_without_additions() -> None:
    candidate = {"eval_additions": []}
    diff = "+++ b/.agent-lab/harness/manifest.json\n+{}\n"
    reason = eval_surface_gate_reason(candidate, diff)
    assert reason is not None
    assert "manifest" in reason


def test_eval_surface_gate_reason_rejects_new_flag_without_additions() -> None:
    candidate = {"eval_additions": []}
    diff = "+++ b/x.py\n+FOO = os.getenv('AGENT_LAB_TOTALLY_NEW_FLAG')\n"
    reason = eval_surface_gate_reason(candidate, diff)
    assert reason is not None
    assert "flag" in reason


def test_eval_surface_gate_reason_passes_ordinary_diff() -> None:
    candidate = {"eval_additions": []}
    assert eval_surface_gate_reason(candidate, _SAMPLE_DIFF) is None


# ---------------------------------------------------------------------------
# worktree mechanics (real git, scratch repo — mirrors test_plan_execute_worktree.py)
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return r.stdout.strip()


@pytest.fixture
def scratch_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "src" / "agent_lab" / "run").mkdir(parents=True)
    (repo / "src" / "agent_lab" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "agent_lab" / "run" / "__init__.py").write_text("", encoding="utf-8")
    # Tier A glob "src/agent_lab/run/profile.py" — real manifest entry, so
    # propose_candidate() accepts this file for the end-to-end tests below.
    (repo / "src" / "agent_lab" / "run" / "profile.py").write_text("MARKER = 'original'\n", encoding="utf-8")
    (repo / "tests").mkdir()
    # Asserts the *patched* value — this is the assertion a candidate declares
    # to prove its fix landed, so it must fail against unpatched/wrongly-patched
    # code and only pass once the diff correctly sets MARKER = 'patched'.
    (repo / "tests" / "test_marker.py").write_text(
        "def test_marker():\n    from agent_lab.run import profile\n    assert profile.MARKER == 'patched'\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-m", "init")
    return repo


def test_create_and_remove_regression_worktree(scratch_repo) -> None:
    wt = create_regression_worktree(scratch_repo, label="test1")
    try:
        assert wt.is_dir()
        assert (wt / "src" / "agent_lab" / "__init__.py").is_file()
    finally:
        remove_regression_worktree(scratch_repo, wt)
    assert not wt.exists()


def test_apply_diff_success(scratch_repo) -> None:
    diff_path = scratch_repo / "change.patch"
    diff_path.write_text(
        "--- a/src/agent_lab/run/profile.py\n"
        "+++ b/src/agent_lab/run/profile.py\n"
        "@@ -1 +1 @@\n"
        "-MARKER = 'original'\n"
        "+MARKER = 'patched'\n",
        encoding="utf-8",
    )
    wt = create_regression_worktree(scratch_repo, label="test2")
    try:
        ok, err = apply_diff(wt, diff_path)
        assert ok, err
        assert "patched" in (wt / "src" / "agent_lab" / "run" / "profile.py").read_text(encoding="utf-8")
    finally:
        remove_regression_worktree(scratch_repo, wt)


def test_apply_diff_missing_file_fails(scratch_repo) -> None:
    wt = create_regression_worktree(scratch_repo, label="test3")
    try:
        ok, err = apply_diff(wt, scratch_repo / "missing.patch")
        assert ok is False
        assert "missing" in err.lower() or "not" in err.lower()
    finally:
        remove_regression_worktree(scratch_repo, wt)


# ---------------------------------------------------------------------------
# run_regression_gate — structural rejections (no worktree needed)
# ---------------------------------------------------------------------------


def _clear_stop_env() -> None:
    # A prior test elsewhere in this xdist worker may have leaked
    # AGENT_LAB_MOCK_AGENTS=1 via raw os.environ (run_dogfood_suite.run_mock()
    # sets it without monkeypatch, never unset) — clear it so the STOP guard
    # doesn't spuriously block propose_candidate() here.
    os.environ.pop("AGENT_LAB_MOCK_AGENTS", None)
    os.environ["AGENT_LAB_RUN_PROFILE"] = "balanced"


def _propose_and_write(tmp_path, **overrides) -> str:
    _clear_stop_env()
    defaults = dict(
        pattern_id="fp:weak_taste:standard",
        axis="profile",
        files=["src/agent_lab/run/profile.py"],
        diff_ref="x.patch",
        assertions=["tests/test_x.py::test_x"],
        root=tmp_path,
    )
    defaults.update(overrides)
    candidate = propose_candidate(**defaults)
    write_candidate(candidate, root=tmp_path)
    return candidate.id


def test_run_regression_gate_rejects_missing_assertions(tmp_path) -> None:
    cid = _propose_and_write(tmp_path, assertions=[])
    report = run_regression_gate(cid, diff_path=tmp_path / "nope.patch", git_root=tmp_path, root=tmp_path)
    assert report.verdict == "fail"
    assert "HS4-1" in report.reason


def test_run_regression_gate_rejects_missing_diff_file(tmp_path) -> None:
    cid = _propose_and_write(tmp_path)
    report = run_regression_gate(cid, diff_path=tmp_path / "nope.patch", git_root=tmp_path, root=tmp_path)
    assert report.verdict == "fail"
    assert "diff file not found" in report.reason


def test_run_regression_gate_rejects_undeclared_files(tmp_path) -> None:
    cid = _propose_and_write(tmp_path)
    diff_path = tmp_path / "x.patch"
    diff_path.write_text("+++ b/src/agent_lab/room/preset.py\n+x = 1\n", encoding="utf-8")
    report = run_regression_gate(cid, diff_path=diff_path, git_root=tmp_path, root=tmp_path)
    assert report.verdict == "fail"
    assert "undeclared files" in report.reason


def test_run_regression_gate_writes_report_on_rejection(tmp_path) -> None:
    from agent_lab.regression_gate import _report_path

    cid = _propose_and_write(tmp_path, assertions=[])
    run_regression_gate(cid, diff_path=tmp_path / "nope.patch", git_root=tmp_path, root=tmp_path)
    assert _report_path(cid, root=tmp_path).is_file()  # HS4-5 — negative result preserved


# ---------------------------------------------------------------------------
# run_regression_gate — full success path (real worktree, real tiny pytest run)
# ---------------------------------------------------------------------------


def test_run_regression_gate_end_to_end_pass(scratch_repo, monkeypatch) -> None:
    """Real worktree + real diff apply + real (tiny) pytest run, verifying the
    PYTHONPATH isolation actually shadows the main checkout (not just mocked)."""
    monkeypatch.chdir(scratch_repo)
    _clear_stop_env()
    root = scratch_repo

    diff_path = root / "change.patch"
    diff_path.write_text(
        "--- a/src/agent_lab/run/profile.py\n"
        "+++ b/src/agent_lab/run/profile.py\n"
        "@@ -1 +1 @@\n"
        "-MARKER = 'original'\n"
        "+MARKER = 'patched'\n",
        encoding="utf-8",
    )

    candidate = propose_candidate(
        pattern_id="fp:weak_taste:standard",
        axis="profile",
        files=["src/agent_lab/run/profile.py"],
        diff_ref=str(diff_path),
        assertions=["tests/test_marker.py::test_marker"],
        root=root,
    )
    write_candidate(candidate, root=root)

    from agent_lab import regression_gate as rg

    # Held-out/smoke would run the REAL 2700-test suite / smoke_room.py against
    # this throwaway scratch repo (which has neither) — stub those two only,
    # keep the assertion runner (HS4-1, the actual gate) real.
    monkeypatch.setattr(rg, "run_held_out", lambda wt, **kw: {"scope": "stub", "pass": True, "detail": ""})
    monkeypatch.setattr(rg, "run_smoke_signal", lambda wt: {"pass": True, "detail": ""})

    report = run_regression_gate(candidate.id, diff_path=diff_path, git_root=root, root=root)

    assert report.verdict == "pass", report.reason
    assert len(report.assertions) == 1
    assert report.assertions[0]["passed"] is True
    assert report.assertions[0]["node_id"] == "tests/test_marker.py::test_marker"


def test_run_regression_gate_end_to_end_fail_assertion(scratch_repo, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    _clear_stop_env()
    root = scratch_repo

    # Patch to something that BREAKS the assertion (test expects 'original').
    diff_path = root / "change.patch"
    diff_path.write_text(
        "--- a/src/agent_lab/run/profile.py\n"
        "+++ b/src/agent_lab/run/profile.py\n"
        "@@ -1 +1 @@\n"
        "-MARKER = 'original'\n"
        "+MARKER = 'broken'\n",
        encoding="utf-8",
    )

    candidate = propose_candidate(
        pattern_id="fp:weak_taste:standard",
        axis="profile",
        files=["src/agent_lab/run/profile.py"],
        diff_ref=str(diff_path),
        assertions=["tests/test_marker.py::test_marker"],
        root=root,
    )
    write_candidate(candidate, root=root)

    from agent_lab import regression_gate as rg

    monkeypatch.setattr(rg, "run_held_out", lambda wt, **kw: {"scope": "stub", "pass": True, "detail": ""})
    monkeypatch.setattr(rg, "run_smoke_signal", lambda wt: {"pass": True, "detail": ""})

    report = run_regression_gate(candidate.id, diff_path=diff_path, git_root=root, root=root)

    assert report.verdict == "fail"
    assert report.assertions[0]["passed"] is False


def test_load_candidate_roundtrip(tmp_path) -> None:
    cid = _propose_and_write(tmp_path)
    data = load_candidate(cid, root=tmp_path)
    assert data["id"] == cid
    assert data["assertions"] == ["tests/test_x.py::test_x"]
