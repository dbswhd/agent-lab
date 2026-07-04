"""P3: kimi_work through Room _call_one_agent — tool_* SSE without Room special cases."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _mock_kimi_work(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: tmp_path)
    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path / "share"))
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")


def test_call_one_agent_kimi_work_emits_tool_sse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from agent_lab.room import agent_invoke
    from agent_lab.run.meta import write_run_meta

    folder = tmp_path / "sess"
    folder.mkdir()
    ws = tmp_path / "worktree"
    ws.mkdir()
    write_run_meta(folder, {})

    monkeypatch.setattr("agent_lab.agents.registry.model_label", lambda agent: agent)
    monkeypatch.setattr(
        "agent_lab.room.messages.build_agent_context_bundle",
        lambda *a, **k: type(
            "B",
            (),
            {
                "render": lambda self: "payload",
                "meta": type("M", (), {"to_dict": lambda self: {}})(),
            },
        )(),
    )

    events: list[tuple[str, dict]] = []

    def on_event(typ: str, payload: dict) -> None:
        events.append((typ, payload))

    msg = agent_invoke._call_one_agent(
        "kimi_work",
        topic="[mock-tools] probe workspace tools",
        thread=[],
        parallel_round=1,
        permissions={"_discuss_cwd": str(ws)},
        review_mode=False,
        review_advocate=None,
        plan_md="",
        run_meta={"_session_folder": str(folder)},
        on_event=on_event,
        human_turn_index=0,
    )

    kinds = [k for k, _ in events]
    assert msg.role == "agent"
    assert "Tool turn complete." in (msg.content or "")
    assert "agent_start" in kinds
    assert "tool_start" in kinds
    assert "tool_output" in kinds
    assert "tool_done" in kinds
    assert "agent_done" in kinds
    tool_starts = [p for k, p in events if k == "tool_start"]
    assert tool_starts
    assert all(p["agent"] == "kimi_work" for p in tool_starts)
    assert any(p["tool"] == "workspace" for p in tool_starts)
    read_start = next(p for p in tool_starts if p["tool"] == "read_file")
    assert read_start["agent"] == "kimi_work"
    done_idx = kinds.index("agent_done")
    tool_done_idx = kinds.index("tool_done")
    assert tool_done_idx < done_idx
