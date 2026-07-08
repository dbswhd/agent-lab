"""HS5 MERGE — merge_gate.py unit tests (mock-only + real-git scratch repos)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agent_lab.harness_proposer import propose_candidate, write_candidate
from agent_lab.merge_gate import (
    MergeRejected,
    audit_eval_case_diff,
    current_harness_rev,
    handle_harness_patch_resolve,
    harness_inbox_enabled,
    harness_patch_stats,
    load_merge_record,
    load_predictions,
    merge_candidate,
    propose_harness_patch,
    record_prediction,
    rollback_harness_patch,
    verify_prediction,
)
from agent_lab.regression_gate import RegressionGateReport, write_report
from agent_lab.wisdom.playbook import add_bullet, load_bullets


def test_harness_inbox_enabled_default_off(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_HARNESS_INBOX", raising=False)
    assert harness_inbox_enabled() is False
    monkeypatch.setenv("AGENT_LAB_HARNESS_INBOX", "1")
    assert harness_inbox_enabled() is True


# ---------------------------------------------------------------------------
# predictions.jsonl (HS5-4)
# ---------------------------------------------------------------------------


def test_record_and_load_predictions(tmp_path) -> None:
    record_prediction("pc-1", predicted_effect={"kpi": "x"}, root=tmp_path)
    rows = load_predictions(tmp_path)
    assert len(rows) == 1
    assert rows[0]["verified"] is None
    assert rows[0]["actual_effect"] is None


def test_verify_prediction_appends_revision_and_folds_latest(tmp_path) -> None:
    record_prediction("pc-1", predicted_effect={"kpi": "x"}, root=tmp_path)
    verify_prediction("pc-1", verified=True, actual_effect={"kpi": "x", "observed": "down"}, root=tmp_path)
    rows = load_predictions(tmp_path)
    assert len(rows) == 1  # folds to latest per candidate_id
    assert rows[0]["verified"] is True
    assert rows[0]["actual_effect"] == {"kpi": "x", "observed": "down"}


def test_verify_prediction_without_prior_record_rejected(tmp_path) -> None:
    with pytest.raises(MergeRejected):
        verify_prediction("pc-missing", verified=True, root=tmp_path)


# ---------------------------------------------------------------------------
# current_harness_rev
# ---------------------------------------------------------------------------


def test_current_harness_rev_fails_open_on_non_git_dir(tmp_path) -> None:
    from agent_lab.wisdom.playbook import HARNESS_REV_UNSET

    assert current_harness_rev(tmp_path) == HARNESS_REV_UNSET


# ---------------------------------------------------------------------------
# HS5-B3 eval case removal audit
# ---------------------------------------------------------------------------


def test_audit_eval_case_diff_allows_pure_addition() -> None:
    diff = '+++ b/evals/cases.jsonl\n+{"id": "new-case"}\n'
    assert audit_eval_case_diff(diff) is None


def test_audit_eval_case_diff_rejects_removal() -> None:
    diff = '--- a/evals/cases.jsonl\n+++ b/evals/cases.jsonl\n-{"id": "existing-case", "x": 1}\n'
    reason = audit_eval_case_diff(diff)
    assert reason is not None
    assert "existing-case" in reason


def test_audit_eval_case_diff_ignores_unrelated_files() -> None:
    diff = "+++ b/src/agent_lab/run/profile.py\n-{\"id\": \"whatever\"}\n"
    assert audit_eval_case_diff(diff) is None


# ---------------------------------------------------------------------------
# real-git scratch repo (mirrors test_regression_gate.py's fixture)
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check)


@pytest.fixture
def scratch_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / ".gitignore").write_text(".agent-lab/\n", encoding="utf-8")
    (repo / "src" / "agent_lab" / "run").mkdir(parents=True)
    (repo / "src" / "agent_lab" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "agent_lab" / "run" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "agent_lab" / "run" / "profile.py").write_text("MARKER = 'original'\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-m", "init")
    return repo


def _seed_candidate_with_passing_report(root: Path, *, tier_files=None, axis="profile") -> tuple[str, Path]:
    """Propose a candidate + write a passing regression report for it — the
    minimum HS5 needs to consider a candidate merge-eligible."""
    import os

    os.environ.pop("AGENT_LAB_MOCK_AGENTS", None)
    os.environ["AGENT_LAB_RUN_PROFILE"] = "balanced"

    diff_path = root / ".agent-lab" / "harness" / "change.patch"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    files = tier_files or ["src/agent_lab/run/profile.py"]
    candidate = propose_candidate(
        pattern_id="fp:weak_taste:standard",
        axis=axis,
        files=files,
        diff_ref=str(diff_path),
        assertions=["tests/test_marker.py::test_marker"],
        root=root,
    )
    write_candidate(candidate, root=root)
    report = RegressionGateReport(
        candidate_id=candidate.id,
        held_in={"topics": [], "source_patterns": []},
        held_out={"pass": True},
        smoke={"pass": True},
        resolved_patterns_checked=[],
        eval_surface_expanded=False,
        assertions=[{"node_id": "tests/test_marker.py::test_marker", "passed": True, "detail": ""}],
        verdict="pass",
        reason="all green",
        generated_at="2026-07-09T00:00:00+00:00",
    )
    write_report(report, root=root)
    return candidate.id, diff_path


def _write_marker_diff(diff_path: Path, *, new_value: str) -> None:
    diff_path.write_text(
        "--- a/src/agent_lab/run/profile.py\n"
        "+++ b/src/agent_lab/run/profile.py\n"
        "@@ -1 +1 @@\n"
        "-MARKER = 'original'\n"
        f"+MARKER = '{new_value}'\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# merge_candidate
# ---------------------------------------------------------------------------


def test_merge_candidate_success(scratch_repo, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    candidate_id, diff_path = _seed_candidate_with_passing_report(scratch_repo)
    _write_marker_diff(diff_path, new_value="patched")

    result = merge_candidate(candidate_id, git_root=scratch_repo, root=scratch_repo)

    assert result["status"] == "merged"
    assert result["merge_commit_sha"]
    content = (scratch_repo / "src" / "agent_lab" / "run" / "profile.py").read_text(encoding="utf-8")
    assert "patched" in content
    log = _git(scratch_repo, "log", "--oneline", "-1").stdout
    assert candidate_id in log

    record = load_merge_record(candidate_id, root=scratch_repo)
    assert record["status"] == "merged"


def test_merge_candidate_dry_run_does_not_write(scratch_repo, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    candidate_id, diff_path = _seed_candidate_with_passing_report(scratch_repo)
    _write_marker_diff(diff_path, new_value="patched")

    result = merge_candidate(candidate_id, git_root=scratch_repo, root=scratch_repo, dry_run=True)

    assert result["status"] == "dry_run"
    content = (scratch_repo / "src" / "agent_lab" / "run" / "profile.py").read_text(encoding="utf-8")
    assert "original" in content  # unchanged


def test_merge_candidate_rejects_without_regression_report(scratch_repo, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    import os

    os.environ.pop("AGENT_LAB_MOCK_AGENTS", None)
    os.environ["AGENT_LAB_RUN_PROFILE"] = "balanced"
    candidate = propose_candidate(
        pattern_id="fp:x",
        axis="profile",
        files=["src/agent_lab/run/profile.py"],
        diff_ref="x.patch",
        root=scratch_repo,
    )
    write_candidate(candidate, root=scratch_repo)

    with pytest.raises(MergeRejected, match="no passing regression report"):
        merge_candidate(candidate.id, git_root=scratch_repo, root=scratch_repo)
    assert load_merge_record(candidate.id, root=scratch_repo)["status"] == "rejected"


def test_merge_candidate_rejects_dirty_working_tree(scratch_repo, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    candidate_id, diff_path = _seed_candidate_with_passing_report(scratch_repo)
    _write_marker_diff(diff_path, new_value="patched")
    (scratch_repo / "untracked_dirty.txt").write_text("oops\n", encoding="utf-8")

    with pytest.raises(MergeRejected, match="uncommitted changes"):
        merge_candidate(candidate_id, git_root=scratch_repo, root=scratch_repo)


def test_merge_candidate_rejects_stale_diff(scratch_repo, monkeypatch) -> None:
    """Freshness check: the file changed on main since REGRESS ran, so the
    diff no longer applies cleanly — merge must not force it through."""
    monkeypatch.chdir(scratch_repo)
    candidate_id, diff_path = _seed_candidate_with_passing_report(scratch_repo)
    _write_marker_diff(diff_path, new_value="patched")

    # Drift main past what the diff expects.
    (scratch_repo / "src" / "agent_lab" / "run" / "profile.py").write_text("MARKER = 'drifted'\n", encoding="utf-8")
    _git(scratch_repo, "add", ".")
    _git(scratch_repo, "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-m", "drift")

    with pytest.raises(MergeRejected, match="git apply failed"):
        merge_candidate(candidate_id, git_root=scratch_repo, root=scratch_repo)


def test_merge_candidate_blocked_by_stop_guard(scratch_repo, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    candidate_id, diff_path = _seed_candidate_with_passing_report(scratch_repo)
    _write_marker_diff(diff_path, new_value="patched")
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")

    with pytest.raises(MergeRejected, match="STOP guard"):
        merge_candidate(candidate_id, git_root=scratch_repo, root=scratch_repo)


def test_merge_candidate_records_resolved_pattern(scratch_repo, monkeypatch) -> None:
    from agent_lab.regression_gate import load_resolved_patterns

    monkeypatch.chdir(scratch_repo)
    candidate_id, diff_path = _seed_candidate_with_passing_report(scratch_repo)
    _write_marker_diff(diff_path, new_value="patched")

    merge_candidate(candidate_id, git_root=scratch_repo, root=scratch_repo)

    rows = load_resolved_patterns(scratch_repo)
    assert any(r["pattern_id"] == "fp:weak_taste:standard" for r in rows)


def test_merge_candidate_records_prediction(scratch_repo, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    candidate_id, diff_path = _seed_candidate_with_passing_report(scratch_repo)
    _write_marker_diff(diff_path, new_value="patched")

    merge_candidate(candidate_id, git_root=scratch_repo, root=scratch_repo)

    predictions = load_predictions(scratch_repo)
    assert any(p["candidate_id"] == candidate_id for p in predictions)


# ---------------------------------------------------------------------------
# HS5-B3 wired into merge_candidate for Tier B
# ---------------------------------------------------------------------------


def test_merge_candidate_tier_b_rejects_eval_case_removal(scratch_repo, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    (scratch_repo / "evals").mkdir()
    (scratch_repo / "evals" / "cases.jsonl").write_text('{"id": "existing-case"}\n', encoding="utf-8")
    _git(scratch_repo, "add", ".")
    _git(scratch_repo, "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-m", "seed eval cases")

    candidate_id, diff_path = _seed_candidate_with_passing_report(
        scratch_repo, tier_files=["evals/cases.jsonl"], axis="eval_surface"
    )
    diff_path.write_text(
        '--- a/evals/cases.jsonl\n+++ b/evals/cases.jsonl\n@@ -1 +0,0 @@\n-{"id": "existing-case"}\n',
        encoding="utf-8",
    )

    with pytest.raises(MergeRejected, match="HS5-B3"):
        merge_candidate(candidate_id, git_root=scratch_repo, root=scratch_repo)


# ---------------------------------------------------------------------------
# rollback_harness_patch (HS5-7)
# ---------------------------------------------------------------------------


def test_rollback_harness_patch_reverts_and_quarantines(scratch_repo, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    candidate_id, diff_path = _seed_candidate_with_passing_report(scratch_repo)
    _write_marker_diff(diff_path, new_value="patched")

    merged = merge_candidate(candidate_id, git_root=scratch_repo, root=scratch_repo)
    harness_rev = merged["harness_rev"]

    playbook_path = scratch_repo / ".agent-lab" / "wisdom" / "playbook.jsonl"
    add_bullet("some lesson", "fp:other:pattern", harness_rev=harness_rev, path=playbook_path)

    result = rollback_harness_patch(candidate_id, git_root=scratch_repo, root=scratch_repo)

    assert result["status"] == "rolled_back"
    assert result["quarantined_bullets"]
    content = (scratch_repo / "src" / "agent_lab" / "run" / "profile.py").read_text(encoding="utf-8")
    assert "original" in content  # revert restored it

    active = load_bullets(status="active", path=playbook_path)
    assert active == []
    quarantined = load_bullets(status="quarantined", path=playbook_path)
    assert len(quarantined) == 1

    record = load_merge_record(candidate_id, root=scratch_repo)
    assert record["status"] == "rolled_back"


def test_rollback_harness_patch_rejects_never_merged(scratch_repo) -> None:
    with pytest.raises(MergeRejected, match="never merged"):
        rollback_harness_patch("pc-nonexistent", git_root=scratch_repo, root=scratch_repo)


# ---------------------------------------------------------------------------
# Inbox integration (propose + resolve)
# ---------------------------------------------------------------------------


@pytest.fixture
def session_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "session"
    folder.mkdir()
    (folder / "run.json").write_text("{}", encoding="utf-8")
    return folder


def test_propose_harness_patch_requires_passing_report(scratch_repo, session_folder, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    import os

    os.environ.pop("AGENT_LAB_MOCK_AGENTS", None)
    os.environ["AGENT_LAB_RUN_PROFILE"] = "balanced"
    candidate = propose_candidate(
        pattern_id="fp:x",
        axis="profile",
        files=["src/agent_lab/run/profile.py"],
        diff_ref="x.patch",
        root=scratch_repo,
    )
    write_candidate(candidate, root=scratch_repo)

    with pytest.raises(MergeRejected):
        propose_harness_patch(candidate.id, session_folder, root=scratch_repo)


def test_propose_harness_patch_creates_inbox_item(scratch_repo, session_folder, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    candidate_id, _ = _seed_candidate_with_passing_report(scratch_repo)

    item = propose_harness_patch(candidate_id, session_folder, root=scratch_repo)

    assert item["kind"] == "harness_patch"
    assert item["refs"][0] == candidate_id
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(session_folder)
    assert len(run.get("human_inbox") or []) == 1


def test_handle_harness_patch_resolve_reject(scratch_repo, session_folder, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    candidate_id, _ = _seed_candidate_with_passing_report(scratch_repo)
    item = propose_harness_patch(candidate_id, session_folder, root=scratch_repo)

    result = handle_harness_patch_resolve(
        session_folder, item, selected=["reject"], status="rejected", root=scratch_repo
    )
    assert result["status"] == "rejected"
    assert load_merge_record(candidate_id, root=scratch_repo)["status"] == "rejected"


def test_handle_harness_patch_resolve_approve_merges(scratch_repo, session_folder, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    candidate_id, diff_path = _seed_candidate_with_passing_report(scratch_repo)
    _write_marker_diff(diff_path, new_value="patched")
    item = propose_harness_patch(candidate_id, session_folder, root=scratch_repo)

    result = handle_harness_patch_resolve(
        session_folder,
        item,
        selected=["approve"],
        status="resolved",
        git_root=scratch_repo,
        root=scratch_repo,
    )
    assert result["status"] == "merged"


def test_handle_harness_patch_resolve_tier_b_rejects_light_approval(scratch_repo, session_folder, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    (scratch_repo / "evals").mkdir()
    (scratch_repo / "evals" / "cases.jsonl").write_text("", encoding="utf-8")
    _git(scratch_repo, "add", ".")
    _git(scratch_repo, "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-m", "seed")

    candidate_id, _ = _seed_candidate_with_passing_report(
        scratch_repo, tier_files=["evals/cases.jsonl"], axis="eval_surface"
    )
    item = propose_harness_patch(candidate_id, session_folder, root=scratch_repo)

    with pytest.raises(MergeRejected, match="HS5-B2"):
        handle_harness_patch_resolve(
            session_folder,
            item,
            selected=["approve"],
            status="resolved",
            git_root=scratch_repo,
            used_light_approval=True,
            root=scratch_repo,
        )


def test_handle_harness_patch_resolve_ignores_other_kinds(session_folder) -> None:
    item = {"kind": "question", "refs": []}
    assert handle_harness_patch_resolve(session_folder, item, selected=None, status="resolved") == {}


# ---------------------------------------------------------------------------
# HS5-5 KPI
# ---------------------------------------------------------------------------


def test_harness_patch_stats_empty(tmp_path) -> None:
    stats = harness_patch_stats(tmp_path)
    assert stats["candidates_decided"] == 0
    assert stats["accept_rate"] is None
    assert stats["prediction_accuracy"] is None


def test_harness_patch_stats_accept_rate(scratch_repo, monkeypatch) -> None:
    monkeypatch.chdir(scratch_repo)
    merged_id, diff_path = _seed_candidate_with_passing_report(scratch_repo)
    _write_marker_diff(diff_path, new_value="patched")
    merge_candidate(merged_id, git_root=scratch_repo, root=scratch_repo)

    import os

    os.environ.pop("AGENT_LAB_MOCK_AGENTS", None)
    rejected = propose_candidate(
        pattern_id="fp:y",
        axis="preset",
        files=["src/agent_lab/room/preset.py"],
        diff_ref="y.patch",
        root=scratch_repo,
    )
    write_candidate(rejected, root=scratch_repo)
    from agent_lab.merge_gate import _write_merge_record

    _write_merge_record(rejected.id, status="rejected", reason="test", root=scratch_repo)

    stats = harness_patch_stats(scratch_repo)
    assert stats["candidates_decided"] == 2
    assert stats["candidates_merged"] == 1
    assert stats["accept_rate"] == 0.5


def test_harness_patch_stats_prediction_accuracy(tmp_path) -> None:
    record_prediction("pc-1", predicted_effect={"kpi": "x"}, root=tmp_path)
    record_prediction("pc-2", predicted_effect={"kpi": "y"}, root=tmp_path)
    verify_prediction("pc-1", verified=True, root=tmp_path)
    verify_prediction("pc-2", verified=False, root=tmp_path)

    stats = harness_patch_stats(tmp_path)
    assert stats["predictions_verified"] == 2
    assert stats["prediction_accuracy"] == 0.5
