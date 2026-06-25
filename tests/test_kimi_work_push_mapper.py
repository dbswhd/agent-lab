"""Kimi Work push mapper — tool SSE from snapshot parts."""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.kimi_work_push_mapper import KimiWorkPushMapper

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kimi_work_tool_pushes.jsonl"


def _load_fixture() -> list[dict]:
    rows: list[dict] = []
    for line in _FIXTURE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def test_fixture_replays_tool_sse() -> None:
    mapper = KimiWorkPushMapper()
    events: list[tuple[str, dict]] = []

    def on_bridge(kind: str, data: dict) -> None:
        events.append((kind, data))

    for row in _load_fixture():
        mapper.emit_push(str(row["method"]), dict(row["params"]), on_bridge)

    kinds = [k for k, _ in events]
    assert "tool_start" in kinds
    assert "tool_output" in kinds
    assert "tool_done" in kinds
    assert "text" in kinds
    assert kinds.count("tool_start") == 1
    assert kinds.count("tool_done") == 1


def test_cumulative_snapshot_dedupes_tool_start() -> None:
    mapper = KimiWorkPushMapper()
    starts = 0

    def on_bridge(kind: str, _data: dict) -> None:
        nonlocal starts
        if kind == "tool_start":
            starts += 1

    part = {
        "kind": "tool-call",
        "toolCallId": "tc1",
        "toolName": "bash",
        "args": "{}",
    }
    payload = {"parts": [part]}
    mapper.emit_push("conversations.message.snapshot", payload, on_bridge)
    mapper.emit_push("conversations.message.snapshot", payload, on_bridge)
    assert starts == 1


def test_cumulative_reply_snapshot_emits_only_delta_text() -> None:
    mapper = KimiWorkPushMapper()
    texts: list[str] = []

    def on_bridge(kind: str, data: dict) -> None:
        if kind == "text":
            texts.append(str(data.get("text") or ""))

    mapper.emit_push(
        "conversations.message.snapshot",
        {"message": {"parts": [{"kind": "text", "text": "Working tree:"}]}},
        on_bridge,
    )
    mapper.emit_push(
        "conversations.message.snapshot",
        {"message": {"parts": [{"kind": "text", "text": "Working tree: clean"}]}},
        on_bridge,
    )
    mapper.emit_push(
        "conversations.message.snapshot",
        {"message": {"parts": [{"kind": "text", "text": "Working tree: clean"}]}},
        on_bridge,
    )
    mapper.emit_push(
        "conversations.message.complete",
        {"message": {"parts": [{"kind": "text", "text": "Working tree: clean"}]}},
        on_bridge,
    )

    assert texts == ["Working tree:", " clean"]


def test_cancelled_emits_activity() -> None:
    mapper = KimiWorkPushMapper()
    events: list[tuple[str, dict]] = []

    def on_bridge(kind: str, data: dict) -> None:
        events.append((kind, data))

    mapper.emit_push(
        "conversations.message.cancelled",
        {"message": "user cancelled"},
        on_bridge,
    )
    assert events == [("activity", {"text": "[system] user cancelled"})]


def test_reasoning_snapshot_emits_thinking_activity_not_text() -> None:
    mapper = KimiWorkPushMapper()
    events: list[tuple[str, dict]] = []

    def on_bridge(kind: str, data: dict) -> None:
        events.append((kind, data))

    payload = {
        "text": "추가 근거 수집: Cursor가 주장한 execute는 cursor|codex만",
        "message": {
            "parts": [
                {
                    "kind": "reasoning",
                    "text": "추가 근거 수집: Cursor가 주장한 execute는 cursor|codex만",
                },
            ],
        },
    }
    mapper.emit_push("conversations.message.snapshot", payload, on_bridge)
    kinds = [k for k, _ in events]
    assert "text" not in kinds
    assert "activity" in kinds
    assert events[-1][1]["text"].startswith("[thinking]")


def test_reasoning_activity_throttles_small_growth() -> None:
    mapper = KimiWorkPushMapper()
    activities: list[str] = []

    def on_bridge(kind: str, data: dict) -> None:
        if kind == "activity":
            activities.append(str(data.get("text") or ""))

    base = {"message": {"parts": [{"kind": "reasoning", "text": "A"}]}}
    mapper.emit_push("conversations.message.snapshot", base, on_bridge)
    mapper.emit_push(
        "conversations.message.snapshot",
        {"message": {"parts": [{"kind": "reasoning", "text": "AB"}]}},
        on_bridge,
    )
    assert len(activities) == 1

    mapper.reset()
    activities.clear()
    mapper.emit_push("conversations.message.snapshot", base, on_bridge)
    mapper.emit_push(
        "conversations.message.snapshot",
        {
            "message": {
                "parts": [
                    {"kind": "reasoning", "text": "A" + ("x" * 30)},
                ],
            },
        },
        on_bridge,
    )
    assert len(activities) == 2
