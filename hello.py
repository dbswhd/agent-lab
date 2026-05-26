#!/usr/bin/env python3
"""Week-1 smoke test: one Planner call on a topic (no LangGraph)."""

import sys

from dotenv import load_dotenv
from agent_lab.invoke import ensure_ready, invoke_role, model_name, provider
from agent_lab.roles import PLANNER


def main() -> int:
    load_dotenv()
    topic = " ".join(sys.argv[1:]).strip() or "Agent Lab hello"
    ensure_ready()
    print(f"# backend: {provider()} ({model_name()})\n", file=sys.stderr)
    print(invoke_role(PLANNER, f"Topic:\n{topic}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
