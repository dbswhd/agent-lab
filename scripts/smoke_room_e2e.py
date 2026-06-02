#!/usr/bin/env python3
"""Mock room E2E: one discuss turn without live LLM (CI-safe)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")


def run_mock_discuss_turn() -> tuple[int, list[str]]:
    from agent_lab.room import continue_room_round

    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agent-lab-e2e-") as tmp:
        folder = Path(tmp) / "2026-05-31-mock-discuss"
        folder.mkdir()
        (folder / "topic.txt").write_text("mock discuss\n", encoding="utf-8")
        (folder / "plan.md").write_text("# plan\n", encoding="utf-8")
        (folder / "chat.jsonl").write_text(
            json.dumps({"role": "user", "content": "seed", "ts": "t0"}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        (folder / "run.json").write_text(
            json.dumps(
                {
                    "workflow_id": "room.parallel",
                    "run_schema_version": 1,
                    "topic": "mock discuss",
                    "agents": ["cursor", "codex", "claude"],
                    "status": "idle",
                    "turns": [],
                    "actions": [],
                    "approvals": [],
                    "executions": [],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        messages, _plan = continue_room_round(
            folder,
            "mock smoke turn",
            agents=["cursor", "codex", "claude"],
            synthesize=False,
            parallel_rounds=1,
        )
        agent_replies = [
            m for m in messages if m.role == "agent" and (m.content or "").strip()
        ]
        if len(agent_replies) < 1:
            errors.append("expected at least one agent reply")
        if not all("[mock:" in (m.content or "") for m in agent_replies):
            errors.append("mock agent prefix missing in replies")

        run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        turns = run.get("turns") or []
        if not turns:
            errors.append("run.json turns[] empty after mock discuss")
        elif turns[-1].get("mode") != "discuss":
            errors.append(f"last turn mode expected discuss, got {turns[-1].get('mode')!r}")

        chat_lines = (folder / "chat.jsonl").read_text(encoding="utf-8").strip().splitlines()
        if len(chat_lines) < 3:
            errors.append("chat.jsonl should contain user + agent lines")

    return (1 if errors else 0), errors


def main() -> int:
    code, errors = run_mock_discuss_turn()
    for err in errors:
        print(f"FAIL: {err}", file=sys.stderr)
    if code == 0:
        print("OK: mock discuss 1-turn E2E")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
