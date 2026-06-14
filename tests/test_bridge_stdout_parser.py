"""Live Cursor bridge stdout → Room SSE event parser."""

from __future__ import annotations

from types import SimpleNamespace

from agent_lab.bridge_stdout_parser import parse_interaction_update, parse_stream_update


def test_text_delta_emits_token_chunks():
    update = SimpleNamespace(type="text-delta", text="Hello ")
    assert parse_interaction_update(update) == [("text", {"text": "Hello "})]


def test_token_delta_is_ignored():
    update = SimpleNamespace(type="token-delta", tokens=3)
    assert parse_interaction_update(update) == []


def test_tool_call_started_emits_tool_start_and_activity():
    update = SimpleNamespace(
        type="tool-call-started",
        tool_call={"name": "read", "args": {"path": "src/room.py"}},
    )
    events = parse_interaction_update(update)
    assert events[0] == ("tool_start", {"tool": "read", "args": {"target": "src/room.py"}})
    assert events[1][0] == "activity"


def test_tool_call_completed_emits_output_and_done():
    update = SimpleNamespace(
        type="tool-call-completed",
        tool_call={"name": "grep", "result": "match line"},
    )
    events = parse_interaction_update(update)
    assert ("tool_output", {"tool": "grep", "chunk": "match line"}) in events
    assert ("tool_done", {"tool": "grep"}) in events


def test_shell_output_delta_emits_tool_output():
    update = SimpleNamespace(
        type="shell-output-delta",
        event={"stdout": "npm test\n"},
    )
    events = parse_interaction_update(update)
    assert events[0] == ("tool_output", {"tool": "shell", "chunk": "npm test\n"})
    assert events[1][0] == "activity"


def test_parse_stream_update_routes_steps():
    step = SimpleNamespace(type="thinkingMessage", message=SimpleNamespace(thinking_duration_ms=1200))
    events = parse_stream_update(step, from_step=True)
    assert events == [("activity", {"text": "Thought briefly"})]


def test_codex_command_started_emits_tool_start():
    event = {
        "type": "item.started",
        "item": {"type": "command_execution", "command": "npm test"},
    }
    from agent_lab.bridge_stdout_parser import parse_codex_json_event

    events = parse_codex_json_event(event)
    assert events[0][0] == "tool_start"
    assert events[0][1]["tool"] == "shell"


def test_claude_stream_event_text_delta():
    event = {
        "type": "stream_event",
        "event": {"delta": {"type": "text_delta", "text": "Hi"}},
    }
    from agent_lab.bridge_stdout_parser import parse_claude_json_event

    assert parse_claude_json_event(event) == [("text", {"text": "Hi"})]


def test_claude_stream_event_tool_use():
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": "src/a.py"}},
            ],
        },
    }
    from agent_lab.bridge_stdout_parser import parse_claude_json_event

    events = parse_claude_json_event(event)
    assert events[0][0] == "tool_start"
    assert events[0][1]["tool"] == "Read"


def test_codex_agent_message_emits_text_chunks():
    event = {
        "type": "item.completed",
        "item": {"type": "agent_message", "text": "Hello from Codex"},
    }
    from agent_lab.bridge_stdout_parser import parse_codex_json_event

    events = parse_codex_json_event(event)
    assert events
    assert all(e[0] == "text" for e in events)
    assert "".join(e[1]["text"] for e in events) == "Hello from Codex"
