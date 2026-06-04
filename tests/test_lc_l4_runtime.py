"""LC-L4 runtime + MD-PROJECT tests."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_adversarial_review_mock_and_injected():
    from agent_lab.adversarial_gate import LGTM_TOKEN, adversarial_review

    out = adversarial_review(
        action_what="add x",
        action_verify="tests pass",
        diff="+ clean",
    )
    assert out["source"] == "mock"
    assert out["note"] == LGTM_TOKEN

    out2 = adversarial_review(
        action_what="add x",
        action_verify="tests pass",
        diff="+ x",
        adversarial_call=lambda _p: "watch edge case",
    )
    assert out2["source"] == "injected"
    assert "edge" in out2["note"]


def test_read_project_md_in_guidance(tmp_path):
    from agent_lab.session_guidance import build_session_guidance_block

    ws = tmp_path / "proj"
    (ws / ".agent-lab").mkdir(parents=True)
    (ws / ".agent-lab" / "PROJECT.md").write_text(
        "# Proj\n\nAlways use typed errors.\n", encoding="utf-8"
    )
    block = build_session_guidance_block(
        {"workspace_binding": {"path": str(ws), "label": "proj"}}
    )
    assert "PROJECT.md" in block
    assert "typed errors" in block
