"""Turn blackboard (turn_state) derivation and payload rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agent_lab.agent.envelope import ENVELOPE_FORMAT_GUIDANCE
from agent_lab.context.bundle import build_context_bundle
from agent_lab.room.turn_state import (
    current_turn_slice,
    derive_turn_state,
    render_turn_state_block,
)


@dataclass
class _Msg:
    role: str
    agent: str | None
    content: str
    parallel_round: int | None = None
    envelope: dict | None = None


def test_envelope_guidance_warns_invalid_fence():
    assert "Invalid" in ENVELOPE_FORMAT_GUIDANCE
    assert "must be JSON" in ENVELOPE_FORMAT_GUIDANCE or "JSON object" in ENVELOPE_FORMAT_GUIDANCE


def test_derive_turn_state_from_smoke_session():
    chat = Path(__file__).resolve().parent / "fixtures" / "envelope_turn_state_chat.jsonl"
    if not chat.is_file():
        return
    rows = [json.loads(ln) for ln in chat.read_text(encoding="utf-8").splitlines() if ln.strip()]
    msgs = [
        _Msg(
            r["role"],
            r.get("agent"),
            r.get("content", ""),
            r.get("parallel_round"),
            r.get("envelope"),
        )
        for r in rows
    ]
    turn, line_base = current_turn_slice(msgs)
    state = derive_turn_state(
        turn,
        line_base=line_base,
        active_agents=["cursor", "codex", "claude"],
        consensus={
            "status": "reached",
            "anchor": {
                "agent": "cursor",
                "excerpt": "Claude TS 선택에 동의",
                "parallel_round": 2,
            },
            "agents_consented": ["codex", "claude"],
        },
    )
    assert state.anchor is not None
    assert state.anchor.get("agent") == "cursor"
    assert len(state.recent_acts) >= 2
    assert any(a.get("act") == "ENDORSE" for a in state.recent_acts)
    block = render_turn_state_block(state)
    assert "[턴 blackboard" in block
    assert "앵커:" in block
    assert "ENDORSE" in block or "합의" in block


def test_context_bundle_includes_turn_state_layer():
    run_meta = {
        "turn_state": {
            "anchor": {
                "agent": "codex",
                "excerpt": "test anchor",
                "parallel_round": 2,
            },
            "recent_acts": [{"agent": "codex", "act": "PROPOSE", "ref": "L3"}],
        }
    }
    bundle = build_context_bundle(
        "topic",
        [_Msg("user", None, "q"), _Msg("agent", "codex", "hi", 1)],
        "cursor",
    )
    # inject via run_meta on second build
    bundle2 = build_context_bundle(
        "topic",
        [_Msg("user", None, "q"), _Msg("agent", "codex", "hi", 1)],
        "cursor",
        run_meta=run_meta,
    )
    assert "[턴 blackboard" not in bundle.render()
    text = bundle2.render()
    assert "[턴 blackboard" in text
    assert bundle2.meta.layer_chars.get("turn_state", 0) > 0
