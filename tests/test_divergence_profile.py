"""발산(divergence) turn-profile contract, catalog, formatter, and injection tests.

Mock-only: no live agents, no network. Covers the spec acceptance criteria for
the divergence turn profile (deep-interview-agent-lab-divergence-mode).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")

from agent_lab.divergence import (
    DIVERGENCE_PROFILES,
    MAX_DIVERGENCE_OPTIONS,
    format_divergence_options,
    is_divergence_profile,
)
from agent_lab.turn_modes import (
    mode_contract_catalog,
    patch_run_mode_contract,
    resolve_mode_contract,
)


def _contract(profile: str):
    return resolve_mode_contract(
        mode="discuss",
        synthesize=False,
        turn_profile=profile,
        agents=["cursor", "codex", "claude"],
        agent_rounds=1,
        review_mode=False,
        consensus_mode=False,
    )


class _Reply:
    def __init__(self, agent: str, content: str) -> None:
        self.agent = agent
        self.content = content


# --- profile membership / detection -------------------------------------


def test_turn_profiles_membership():
    from app.server.deps import TURN_PROFILES

    assert "divergence" in TURN_PROFILES
    assert "발산" in TURN_PROFILES


@pytest.mark.parametrize(
    "value,expected",
    [
        ("divergence", True),
        ("발산", True),
        (" Divergence ", True),
        ("team", False),
        ("verified", False),
        ("", False),
        (None, False),
    ],
)
def test_is_divergence_profile(value, expected):
    assert is_divergence_profile(value) is expected


def test_divergence_profiles_constant():
    assert DIVERGENCE_PROFILES == frozenset({"divergence", "발산"})


# --- mode contract --------------------------------------------------------


@pytest.mark.parametrize("profile", ["divergence", "발산"])
def test_resolve_divergence_contract(profile):
    c = _contract(profile)
    assert c.divergence is True
    # Divergence must not enter the consensus/convergence machinery.
    assert c.consensus_mode is False
    assert c.review_mode is False
    # plan_intent "none" => no scribe / synthesize / execute-loop path fires.
    assert c.plan_intent == "none"
    assert c.runtime_turn_profile == "divergence"
    assert c.agents == ["cursor", "codex", "claude"]


@pytest.mark.parametrize("profile", ["team", "quick"])
def test_divergence_defaults_false_for_other_profiles(profile):
    assert _contract(profile).divergence is False


def test_loop_profile_unaffected_and_not_divergent():
    c = resolve_mode_contract(
        mode="plan",
        synthesize=True,
        turn_profile="verified",
        agents=["cursor", "codex", "claude"],
        agent_rounds=2,
        review_mode=True,
        consensus_mode=True,
    )
    # Regression: verified/loop governance is untouched by divergence work.
    assert c.divergence is False
    assert c.plan_intent == "loop"


def test_mode_contract_catalog_entry():
    modes = {m["id"]: m for m in mode_contract_catalog()["modes"]}
    assert "divergence" in modes
    entry = modes["divergence"]
    assert entry["divergence"] is True
    assert entry["execute_loop_on_approve"] is False
    assert entry["plan_intent"] == "none"


def test_patch_run_mode_contract_roundtrips_divergence(tmp_path: Path):
    folder = tmp_path
    (folder / "run.json").write_text("{}", encoding="utf-8")
    contract = _contract("발산")
    patch_run_mode_contract(folder, contract)
    import json

    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["divergence_mode"] is True
    assert run["user_mode"] == "team"
    assert run["plan_intent"] == "none"


def test_patch_run_mode_contract_roundtrips_false_for_team(tmp_path: Path):
    folder = tmp_path
    (folder / "run.json").write_text("{}", encoding="utf-8")
    patch_run_mode_contract(folder, _contract("team"))
    import json

    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["divergence_mode"] is False


# --- options formatter (terminal artifact, no execute) --------------------


def test_format_divergence_options_basic():
    replies = [_Reply("cursor", "Approach A"), _Reply("codex", "Approach B"), _Reply("claude", "Approach C")]
    opts = format_divergence_options(replies)
    assert len(opts) == 3
    assert [o["agent"] for o in opts] == ["cursor", "codex", "claude"]
    assert [o["index"] for o in opts] == ["1", "2", "3"]
    assert opts[0]["approach"] == "Approach A"


def test_format_divergence_options_caps_at_max():
    replies = [_Reply(f"a{i}", f"opt{i}") for i in range(10)]
    assert len(format_divergence_options(replies)) == MAX_DIVERGENCE_OPTIONS


def test_format_divergence_options_skips_empty():
    replies = [_Reply("cursor", "  "), _Reply("codex", "real")]
    opts = format_divergence_options(replies)
    assert len(opts) == 1 and opts[0]["agent"] == "codex"


def test_format_divergence_options_accepts_dicts():
    opts = format_divergence_options([{"agent": "cursor", "content": "X"}])
    assert opts == [{"index": "1", "agent": "cursor", "approach": "X"}]


# --- divergence instruction injection (only under divergence profile) -----


def test_divergence_instruction_injected_only_under_divergence():
    from agent_lab.agents.prompts import DIVERGENCE_INSTRUCTION
    from agent_lab.context.bundle import build_context_bundle

    div = build_context_bundle("topic", [], "cursor", run_meta={"turn_profile": "발산"}).render()
    team = build_context_bundle("topic", [], "cursor", run_meta={"turn_profile": "team"}).render()

    assert DIVERGENCE_INSTRUCTION in div
    assert DIVERGENCE_INSTRUCTION not in team
    # Divergence must not also receive the analyze "observe only" instruction.
    assert "[Analyze turn]" not in div


# --- terminal emit (divergence_options event, gated on profile) -----------


def test_emit_divergence_options_only_for_divergence():
    from agent_lab.room.turn_flow import _emit_divergence_options

    events: list[tuple[str, dict]] = []

    def on_event(t, p):
        events.append((t, p))

    replies = [_Reply("cursor", "A"), _Reply("codex", "B")]
    _emit_divergence_options({"turn_profile": "발산"}, replies, on_event, False)
    _emit_divergence_options({"turn_profile": "team"}, replies, on_event, False)
    _emit_divergence_options({"turn_profile": "divergence"}, replies, on_event, True)  # cancelled

    assert len(events) == 1
    assert events[0][0] == "divergence_options"
    assert events[0][1]["count"] == 2
