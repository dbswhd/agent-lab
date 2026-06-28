"""Single entry for role LLM calls (API or Codex CLI)."""

from __future__ import annotations

import os
from contextvars import ContextVar, Token

from agent_lab.codex import cli as codex_cli

_provider_ctx: ContextVar[str | None] = ContextVar("agent_lab_provider", default=None)


def set_provider_override(name: str | None) -> Token[str | None]:
    return _provider_ctx.set(name)


def reset_provider_override(token: Token[str | None]) -> None:
    _provider_ctx.reset(token)


def provider() -> str:
    override = _provider_ctx.get()
    if override in ("codex", "openai", "anthropic"):
        return override
    explicit = (os.getenv("AGENT_LAB_PROVIDER") or "").strip().lower()
    if explicit in ("codex", "openai", "anthropic"):
        return explicit
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if codex_cli.is_available():
        return "codex"
    return ""


def ensure_ready() -> None:
    p = provider()
    if p == "codex":
        if not codex_cli.is_available():
            raise RuntimeError("Codex CLI not found. Run: npm i -g @openai/codex && codex login")
        return
    if p in ("openai", "anthropic"):
        from agent_lab.llm import get_llm

        get_llm()
        return
    raise RuntimeError(
        "No backend. Use AGENT_LAB_PROVIDER=codex (Plus via `codex login`), "
        "or set OPENAI_API_KEY / ANTHROPIC_API_KEY in .env"
    )


def model_name() -> str:
    p = provider()
    if p == "codex":
        return codex_cli.model_label()
    from agent_lab.llm import model_name as api_model_name

    return api_model_name()


def invoke_role(system: str, user: str) -> str:
    p = provider()
    if p == "codex":
        return codex_cli.invoke(system, user)
    from agent_lab.llm import get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm()
    msg = llm.invoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=user),
        ]
    )
    return (msg.content or "").strip()
