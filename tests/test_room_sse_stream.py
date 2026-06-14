"""M2: room SSE streaming contract — agent_token + tool_* events."""

from __future__ import annotations


from agent_mocks import patch_call_agent_reply

from agent_lab.room_sse_stream import (
    chunk_text,
    emit_agent_tokens,
    format_tool_activity_line,
    maybe_emit_tool_events,
)


def test_chunk_text_splits_body():
    assert chunk_text("abcdef", chunk_size=2) == ["ab", "cd", "ef"]
    assert chunk_text("", chunk_size=4) == []


def test_emit_agent_tokens_sequence():
    events: list[tuple[str, dict]] = []

    def emit(typ: str, payload: dict) -> None:
        events.append((typ, payload))

    emit_agent_tokens(
        emit,
        agent="cursor",
        round=1,
        text="hello world",
        chunk_size=5,
    )
    assert [e[0] for e in events] == ["agent_token", "agent_token", "agent_token"]
    assert "".join(e[1]["text"] for e in events) == "hello world"
    assert all(e[1]["agent"] == "cursor" and e[1]["round"] == 1 for e in events)


def test_maybe_emit_tool_events_bracket_line():
    events: list[tuple[str, dict]] = []

    def emit(typ: str, payload: dict) -> None:
        events.append((typ, payload))

    maybe_emit_tool_events(
        emit,
        agent="codex",
        round=2,
        line="[tool · read] src/agent_lab/room.py",
    )
    assert [e[0] for e in events] == ["tool_start", "tool_output", "tool_done"]
    assert events[0][1]["tool"] == "read"
    assert events[0][1]["args"]["target"] == "src/agent_lab/room.py"


def test_maybe_emit_tool_events_cli_prefix():
    events: list[tuple[str, dict]] = []

    def emit(typ: str, payload: dict) -> None:
        events.append((typ, payload))

    maybe_emit_tool_events(
        emit,
        agent="claude",
        round=1,
        line="Read README.md",
    )
    assert events[0][1]["tool"] == "read"
    assert events[1][1]["chunk"] == "Read README.md"


def test_format_tool_activity_line():
    assert format_tool_activity_line(tool="grep", args="agent_token") == (
        "[tool · grep] agent_token"
    )


def test_call_one_agent_emits_live_bridge_tokens_before_done(monkeypatch, tmp_path):
    from agent_lab import room

    folder = tmp_path / "sess"
    folder.mkdir()
    from agent_lab.run_meta import write_run_meta

    write_run_meta(folder, {})

    def fake_reply(*_a, **kwargs):
        on_bridge = kwargs.get("on_bridge_event")
        if on_bridge:
            on_bridge("text", {"text": "live "})
            on_bridge("text", {"text": "stream"})
        return type("R", (), {"text": "live stream", "structured_envelope": None})()

    monkeypatch.setattr("agent_lab.agents.registry.call_agent_reply", fake_reply)
    monkeypatch.setattr(room, "model_label", lambda agent: agent)
    monkeypatch.setattr(
        room,
        "build_agent_context_bundle",
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

    room._call_one_agent(
        "cursor",
        topic="t",
        thread=[],
        parallel_round=1,
        permissions=None,
        review_mode=False,
        review_advocate=None,
        plan_md="",
        run_meta={"_session_folder": str(folder)},
        on_event=on_event,
        human_turn_index=0,
    )
    token_texts = [e[1]["text"] for e in events if e[0] == "agent_token"]
    assert token_texts == ["live ", "stream"]
    assert "agent_done" in [e[0] for e in events]
    assert sum(1 for e in events if e[0] == "agent_token") == 2


def test_call_one_agent_emits_agent_token_before_done(monkeypatch, tmp_path):
    from agent_lab import room

    folder = tmp_path / "sess"
    folder.mkdir()
    from agent_lab.run_meta import write_run_meta

    write_run_meta(folder, {})

    patch_call_agent_reply(
        monkeypatch,
        lambda *_a, **_k: "[mock:cursor] streaming body for test",
    )
    monkeypatch.setattr(room, "model_label", lambda agent: agent)
    monkeypatch.setattr(
        room,
        "build_agent_context_bundle",
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

    run_meta = {"_session_folder": str(folder)}
    msg = room._call_one_agent(
        "cursor",
        topic="t",
        thread=[],
        parallel_round=1,
        permissions=None,
        review_mode=False,
        review_advocate=None,
        plan_md="",
        run_meta=run_meta,
        on_event=on_event,
        human_turn_index=0,
    )
    assert msg.role == "agent"
    types = [e[0] for e in events]
    assert "agent_start" in types
    assert "agent_token" in types
    assert "agent_done" in types
    token_idx = types.index("agent_token")
    done_idx = types.index("agent_done")
    assert token_idx < done_idx
    streamed = "".join(
        e[1]["text"] for e in events if e[0] == "agent_token"
    )
    done = next(e for e in events if e[0] == "agent_done")
    assert streamed == done[1]["content"]
    assert "streaming body" in streamed
