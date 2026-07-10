from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_lab.graph import GraphState

from agent_lab.time_utils import utc_now_iso, utc_now
from agent_lab.session.paths import SESSIONS_DIR, active_sessions_dir, sessions_dir  # noqa: F401


def slugify(topic: str) -> str:
    s = topic.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return (s[:48] or "topic").rstrip("-")


def _sessions_root(base: Path | None = None) -> Path:
    if base is not None:
        return base
    return active_sessions_dir()


def session_dir(topic: str, base: Path | None = None) -> Path:
    root = _sessions_root(base)
    day = utc_now().strftime("%Y-%m-%d")
    name = f"{day}-{slugify(topic)}"
    path = root / name
    if path.exists():
        n = 2
        while (root / f"{name}-{n}").exists():
            n += 1
        path = root / f"{name}-{n}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def build_transcript(state: GraphState) -> str:
    return "\n\n".join(
        [
            f"# Session transcript\n\n**Topic:** {state['topic']}\n",
            "## Planner\n\n" + state["planner_output"],
            "## Critic\n\n" + state["critic_output"],
            "## Scribe (plan)\n\n" + state["plan_md"],
        ]
    )


def save_session(state: GraphState, base: Path | None = None) -> Path:
    from agent_lab.invoke import model_name

    folder = session_dir(state["topic"], base=base)
    now = utc_now_iso()

    (folder / "topic.txt").write_text(state["topic"].strip() + "\n", encoding="utf-8")
    (folder / "plan.md").write_text(state["plan_md"] + "\n", encoding="utf-8")
    (folder / "transcript.md").write_text(build_transcript(state), encoding="utf-8")
    meta = {
        "topic": state["topic"],
        "created_at": now,
        "model": model_name(),
        "nodes": ["planner", "critic", "scribe"],
        "max_llm_calls": 3,
    }
    (folder / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return folder
