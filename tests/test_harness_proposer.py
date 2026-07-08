"""HS3 PROPOSE — harness_proposer.py unit tests (mock-only)."""

from __future__ import annotations

import json

import pytest

from agent_lab.harness_proposer import (
    ProposalRejected,
    addressable_patterns,
    axis_for_path,
    classify_tier,
    ensure_manifest,
    harness_proposer_enabled,
    load_manifest,
    manifest_path,
    parse_prompt_blocks,
    propose_candidate,
    stop_guard_reason,
    tier_a_globs,
    tier_b_globs,
    write_candidate,
)
from agent_lab.outcome_harvester import append_outcome


def test_harness_proposer_enabled_default_off(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_HARNESS_PROPOSER", raising=False)
    assert harness_proposer_enabled() is False
    monkeypatch.setenv("AGENT_LAB_HARNESS_PROPOSER", "1")
    assert harness_proposer_enabled() is True


# ---------------------------------------------------------------------------
# manifest.json
# ---------------------------------------------------------------------------


def test_load_manifest_returns_defaults_when_absent(tmp_path) -> None:
    manifest = load_manifest(tmp_path)
    globs = [e["glob"] for e in manifest["tiers"]["A"]]
    assert ".claude/skills/**" in globs


def test_ensure_manifest_writes_file_and_is_idempotent(tmp_path) -> None:
    path = ensure_manifest(tmp_path)
    assert path.is_file()
    original = path.read_text(encoding="utf-8")
    ensure_manifest(tmp_path)
    assert path.read_text(encoding="utf-8") == original


def test_manifest_path_resolves_under_root(tmp_path) -> None:
    assert manifest_path(tmp_path) == tmp_path / ".agent-lab" / "harness" / "manifest.json"


def test_tier_a_and_b_globs_from_defaults(tmp_path) -> None:
    assert "src/agent_lab/run/profile.py" in tier_a_globs(root=tmp_path)
    assert "evals/cases.jsonl" in tier_b_globs(root=tmp_path)


# ---------------------------------------------------------------------------
# classify_tier / axis_for_path
# ---------------------------------------------------------------------------


def test_classify_tier_a_for_prompts(tmp_path) -> None:
    assert classify_tier("src/agent_lab/agents/prompts.py", root=tmp_path) == "A"


def test_classify_tier_b_for_eval_cases(tmp_path) -> None:
    assert classify_tier("evals/cases.jsonl", root=tmp_path) == "B"


def test_classify_tier_c_for_frozen_path(tmp_path) -> None:
    assert classify_tier("src/agent_lab/human_inbox.py", root=tmp_path) == "C"


def test_classify_tier_c_for_unregistered_path(tmp_path) -> None:
    assert classify_tier("src/agent_lab/some_random_module.py", root=tmp_path) == "C"


def test_axis_for_path(tmp_path) -> None:
    assert axis_for_path("src/agent_lab/agents/prompts.py", root=tmp_path) == "prompts"
    assert axis_for_path("evals/cases.jsonl", root=tmp_path) == "eval_surface"
    assert axis_for_path("src/agent_lab/human_inbox.py", root=tmp_path) is None


# ---------------------------------------------------------------------------
# HS3-3 prompts BLOCK parser
# ---------------------------------------------------------------------------


def test_parse_prompt_blocks_finds_pairs() -> None:
    text = "\n".join(
        [
            "x = 1",
            "# --- BLOCK: cursor ---",
            "CURSOR = 'a'",
            "# --- END BLOCK: cursor ---",
            "# --- BLOCK: codex ---",
            "CODEX = 'b'",
            "# --- END BLOCK: codex ---",
        ]
    )
    blocks = parse_prompt_blocks(text)
    assert blocks["cursor"] == (2, 4)
    assert blocks["codex"] == (5, 7)


def test_parse_prompt_blocks_on_real_file() -> None:
    from pathlib import Path

    text = Path("src/agent_lab/agents/prompts.py").read_text(encoding="utf-8")
    blocks = parse_prompt_blocks(text)
    assert {"cursor", "codex", "claude", "kimi_work"} <= blocks.keys()
    for start, end in blocks.values():
        assert start < end


def test_parse_prompt_blocks_unclosed_is_dropped() -> None:
    text = "# --- BLOCK: cursor ---\nCURSOR = 'a'\n"
    assert parse_prompt_blocks(text) == {}


def test_parse_prompt_blocks_mismatched_end_is_dropped() -> None:
    text = "# --- BLOCK: cursor ---\nCURSOR = 'a'\n# --- END BLOCK: codex ---\n"
    assert parse_prompt_blocks(text) == {}


# ---------------------------------------------------------------------------
# §7.4 STOP guard
# ---------------------------------------------------------------------------


def test_stop_guard_blocks_on_mock_agents(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    assert stop_guard_reason() is not None


def test_stop_guard_blocks_on_fast_profile(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.setenv("AGENT_LAB_RUN_PROFILE", "fast")
    assert stop_guard_reason() is not None


def test_stop_guard_clear_without_run_meta(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.setenv("AGENT_LAB_RUN_PROFILE", "balanced")
    assert stop_guard_reason() is None


def test_stop_guard_blocks_on_low_autonomy_with_run_meta(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.setenv("AGENT_LAB_RUN_PROFILE", "balanced")
    assert stop_guard_reason(run_meta={}) is not None  # infers L0 by default


# ---------------------------------------------------------------------------
# HS3-4 trigger — addressable_patterns
# ---------------------------------------------------------------------------


def test_addressable_patterns_wraps_weakness_miner(tmp_path) -> None:
    for i in range(3):
        append_outcome({"session_id": f"s{i}", "category": "standard", "primary_tag": "weak_taste"}, root=tmp_path)
    patterns = addressable_patterns(root=tmp_path)
    assert len(patterns) == 1
    assert patterns[0]["pattern_id"] == "fp:weak_taste:standard"


# ---------------------------------------------------------------------------
# propose_candidate
# ---------------------------------------------------------------------------


def _clear_stop_env(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.setenv("AGENT_LAB_RUN_PROFILE", "balanced")


def test_propose_candidate_success(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    candidate = propose_candidate(
        pattern_id="fp:weak_taste:standard",
        axis="profile",
        files=["src/agent_lab/run/profile.py"],
        diff_ref="candidates/pc-1/diff.patch",
        root=tmp_path,
    )
    assert candidate.tier == "A"
    assert candidate.status == "proposed"
    assert candidate.id.startswith("pc-")


def test_propose_candidate_blocked_by_stop_guard(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    with pytest.raises(ProposalRejected, match="STOP guard"):
        propose_candidate(
            pattern_id="fp:x",
            axis="profile",
            files=["src/agent_lab/run/profile.py"],
            diff_ref="x",
            root=tmp_path,
        )


def test_propose_candidate_rejects_empty_files(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    with pytest.raises(ProposalRejected, match="at least one file"):
        propose_candidate(pattern_id="fp:x", axis="profile", files=[], diff_ref="x", root=tmp_path)


def test_propose_candidate_rejects_tier_c_files(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    with pytest.raises(ProposalRejected, match="Tier C"):
        propose_candidate(
            pattern_id="fp:x",
            axis="profile",
            files=["src/agent_lab/human_inbox.py"],
            diff_ref="x",
            root=tmp_path,
        )


def test_propose_candidate_rejects_mixed_tiers(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    with pytest.raises(ProposalRejected, match="multiple tiers"):
        propose_candidate(
            pattern_id="fp:x",
            axis="profile",
            files=["src/agent_lab/run/profile.py", "evals/cases.jsonl"],
            diff_ref="x",
            root=tmp_path,
        )


def test_propose_candidate_rejects_mixed_axes(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    with pytest.raises(ProposalRejected, match="1 candidate = 1 axis"):
        propose_candidate(
            pattern_id="fp:x",
            axis="profile",
            files=["src/agent_lab/run/profile.py", "src/agent_lab/room/preset.py"],
            diff_ref="x",
            root=tmp_path,
        )


def test_propose_candidate_block_scoped_requires_block_name(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    with pytest.raises(ProposalRejected, match="block-scoped"):
        propose_candidate(
            pattern_id="fp:x",
            axis="prompts",
            files=["src/agent_lab/agents/prompts.py"],
            diff_ref="x",
            root=tmp_path,
        )


def test_propose_candidate_block_scoped_validates_against_real_file(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    candidate = propose_candidate(
        pattern_id="fp:x",
        axis="prompts",
        files=["src/agent_lab/agents/prompts.py"],
        diff_ref="x",
        block="cursor",
        root=None,  # real repo root — prompts.py actually has this BLOCK
    )
    assert candidate.axis == "prompts"


def test_propose_candidate_block_scoped_rejects_unknown_block(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    with pytest.raises(ProposalRejected, match="no 'nonexistent_agent' BLOCK"):
        propose_candidate(
            pattern_id="fp:x",
            axis="prompts",
            files=["src/agent_lab/agents/prompts.py"],
            diff_ref="x",
            block="nonexistent_agent",
            root=None,
        )


def test_propose_candidate_new_surface_requires_eval_additions(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    with pytest.raises(ProposalRejected, match="eval_additions"):
        propose_candidate(
            pattern_id="fp:x",
            axis="profile",
            files=["src/agent_lab/run/profile.py"],
            diff_ref="x",
            introduces_new_surface=True,
            root=tmp_path,
        )


def test_propose_candidate_new_surface_with_eval_additions_ok(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    candidate = propose_candidate(
        pattern_id="fp:x",
        axis="profile",
        files=["src/agent_lab/run/profile.py"],
        diff_ref="x",
        introduces_new_surface=True,
        eval_additions=["dogfood-v1.json#M9"],
        root=tmp_path,
    )
    assert candidate.eval_additions == ["dogfood-v1.json#M9"]


# ---------------------------------------------------------------------------
# write_candidate
# ---------------------------------------------------------------------------


def test_write_candidate_persists_json(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    candidate = propose_candidate(
        pattern_id="fp:x",
        axis="profile",
        files=["src/agent_lab/run/profile.py"],
        diff_ref="x",
        root=tmp_path,
    )
    path = write_candidate(candidate, root=tmp_path)
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["id"] == candidate.id
    assert on_disk["status"] == "proposed"


def test_write_candidate_refuses_overwrite(tmp_path, monkeypatch) -> None:
    _clear_stop_env(monkeypatch)
    candidate = propose_candidate(
        pattern_id="fp:x",
        axis="profile",
        files=["src/agent_lab/run/profile.py"],
        diff_ref="x",
        root=tmp_path,
    )
    write_candidate(candidate, root=tmp_path)
    with pytest.raises(FileExistsError):
        write_candidate(candidate, root=tmp_path)
