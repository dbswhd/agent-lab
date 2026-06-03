from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

from agent_lab import claude_cli, codex_cli
from agent_lab.agents.registry import (
    available_agents,
    label as agent_label,
    model_label as agent_model_label,
)
from agent_lab.invoke import provider

router = APIRouter(prefix="/api")


@router.get("/agents")
def agents() -> dict[str, Any]:
    ready = available_agents()
    return {
        "agents": [
            {
                "id": aid,
                "label": agent_label(aid),
                "ready": aid in ready,
                "model": agent_model_label(aid),
            }
            for aid in ("cursor", "codex", "claude")
        ],
        "default": ready,
    }


@router.get("/backends")
def backends() -> dict[str, Any]:
    options = []
    if codex_cli.is_available():
        options.append(
            {
                "id": "codex",
                "label": "Codex (ChatGPT Plus)",
                "ready": True,
            }
        )
    if claude_cli.is_available():
        options.append(
            {
                "id": "claude_code",
                "label": "Claude Code (subscription)",
                "ready": True,
            }
        )
    if os.getenv("OPENAI_API_KEY"):
        options.append({"id": "openai", "label": "OpenAI API", "ready": True})
    if os.getenv("ANTHROPIC_API_KEY"):
        options.append(
            {"id": "anthropic", "label": "Anthropic API", "ready": True}
        )
    return {
        "default": provider() or (options[0]["id"] if options else None),
        "options": options,
    }
