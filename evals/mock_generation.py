from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import os
from pathlib import Path

from evals.schema import EvalCase


@contextmanager
def patched_env(updates: dict[str, str]) -> Generator[None]:
    saved: dict[str, str | None] = {}
    for key, value in updates.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, old_value in saved.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def generate_mock_session(case: EvalCase, generated_dir: Path) -> Path:
    mock_run = case.get("mock_run")
    if mock_run is None:
        raise ValueError("missing mock_run config")
    topic = mock_run.get("topic", "").strip()
    if not topic:
        raise ValueError("mock_run.topic is required")

    from agent_lab import room

    with patched_env(
        {
            "AGENT_LAB_MOCK_AGENTS": "1",
            "AGENT_LAB_CLARIFIER": "0",
            "AGENT_LAB_INBOX_MODE": "soft",
        }
    ):
        folder, _messages, _plan = room.run_room(
            topic,
            agents=["cursor", "codex", "claude"],
            synthesize=True,
            sessions_base=generated_dir,
            consensus_mode=mock_run.get("consensus_mode", False),
            turn_profile=mock_run.get("turn_profile", "analyze"),
        )
    return folder
