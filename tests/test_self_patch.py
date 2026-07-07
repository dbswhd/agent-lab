"""N6 — self-patch allowlist + eligibility classification unit tests.

NORTH-STAR §2.1 N6. Pure classification only — no gate/approval behavior lives
here (that's the point: this is an audit tag, not an autonomy switch).
"""

from __future__ import annotations

from agent_lab.self_patch import (
    classify_self_patch,
    ensure_self_patch_allowlist,
    load_self_patch_allowlist,
    matches_self_patch_allowlist,
    self_patch_allowlist_path,
)


def test_self_patch_allowlist_path_resolves_under_root(tmp_path):
    path = self_patch_allowlist_path(tmp_path)
    assert path == tmp_path / ".agent-lab" / "self_patch_allowlist.txt"


def test_ensure_creates_file_with_default_patterns(tmp_path):
    path = ensure_self_patch_allowlist(tmp_path)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert ".claude/skills/**" in text
    assert "src/agent_lab/agents/prompts.py" in text
    assert "src/agent_lab/run/profile.py" in text


def test_ensure_is_idempotent_does_not_overwrite(tmp_path):
    path = ensure_self_patch_allowlist(tmp_path)
    path.write_text("custom/pattern/*\n", encoding="utf-8")
    ensure_self_patch_allowlist(tmp_path)  # must not clobber human edits
    assert path.read_text(encoding="utf-8") == "custom/pattern/*\n"


def test_load_returns_defaults_when_file_absent(tmp_path):
    patterns = load_self_patch_allowlist(tmp_path)
    assert ".claude/skills/**" in patterns


def test_load_skips_comments_and_blank_lines(tmp_path):
    path = self_patch_allowlist_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# comment\n\nfoo/bar.py\n  \n# another\nbaz/*.py\n", encoding="utf-8")
    assert load_self_patch_allowlist(tmp_path) == ["foo/bar.py", "baz/*.py"]


# --- glob matching ----------------------------------------------------------


def test_doublestar_matches_any_depth():
    assert matches_self_patch_allowlist("a/b/c.md", [".claude/skills/**"]) is False
    assert matches_self_patch_allowlist(".claude/skills/foo/SKILL.md", [".claude/skills/**"]) is True
    assert matches_self_patch_allowlist(".claude/skills/foo/bar/deep.md", [".claude/skills/**"]) is True


def test_exact_file_pattern_matches_only_that_file():
    patterns = ["src/agent_lab/agents/prompts.py"]
    assert matches_self_patch_allowlist("src/agent_lab/agents/prompts.py", patterns) is True
    assert matches_self_patch_allowlist("src/agent_lab/agents/other.py", patterns) is False


def test_single_star_stays_within_one_segment():
    patterns = ["foo/*.py"]
    assert matches_self_patch_allowlist("foo/bar.py", patterns) is True
    assert matches_self_patch_allowlist("foo/nested/bar.py", patterns) is False


def test_leading_slash_and_backslash_normalized():
    patterns = ["foo/*.py"]
    assert matches_self_patch_allowlist("/foo/bar.py", patterns) is True
    assert matches_self_patch_allowlist("foo\\bar.py", ["foo/bar.py"]) is True


def test_core_path_never_matches_default_allowlist(tmp_path):
    ensure_self_patch_allowlist(tmp_path)
    assert matches_self_patch_allowlist("src/agent_lab/room/turn_flow_run.py", root=tmp_path) is False
    assert matches_self_patch_allowlist("src/agent_lab/human_inbox.py", root=tmp_path) is False


# --- classify_self_patch -----------------------------------------------------


def test_classify_empty_touched_paths_not_eligible(tmp_path):
    result = classify_self_patch([], root=tmp_path)
    assert result["eligible"] is False
    assert result["matched"] == []
    assert result["core_paths"] == []


def test_classify_all_allowlisted_is_eligible(tmp_path):
    ensure_self_patch_allowlist(tmp_path)
    result = classify_self_patch([".claude/skills/foo/SKILL.md", "src/agent_lab/run/profile.py"], root=tmp_path)
    assert result["eligible"] is True
    assert result["core_paths"] == []
    assert len(result["matched"]) == 2


def test_classify_one_core_path_disqualifies_whole_set(tmp_path):
    ensure_self_patch_allowlist(tmp_path)
    result = classify_self_patch(
        [".claude/skills/foo/SKILL.md", "src/agent_lab/room/turn_flow_run.py"],
        root=tmp_path,
    )
    assert result["eligible"] is False
    assert result["core_paths"] == ["src/agent_lab/room/turn_flow_run.py"]
    assert result["matched"] == [".claude/skills/foo/SKILL.md"]


def test_classify_includes_patterns_used(tmp_path):
    ensure_self_patch_allowlist(tmp_path)
    result = classify_self_patch(["src/agent_lab/run/profile.py"], root=tmp_path)
    assert ".claude/skills/**" in result["patterns"]
