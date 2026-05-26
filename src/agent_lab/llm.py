import os

from langchain_core.language_models import BaseChatModel


def get_llm() -> BaseChatModel:
    provider = (os.getenv("AGENT_LAB_PROVIDER") or "").strip().lower()
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))

    if provider == "openai" and has_openai:
        return _openai()
    if provider == "anthropic" and has_anthropic:
        return _anthropic()
    if has_openai:
        return _openai()
    if has_anthropic:
        return _anthropic()

    raise RuntimeError(
        "No API key found. Copy .env.example to .env and set "
        "OPENAI_API_KEY and/or ANTHROPIC_API_KEY."
    )


def model_name() -> str:
    provider = (os.getenv("AGENT_LAB_PROVIDER") or "").strip().lower()
    if provider == "anthropic" or (
        not os.getenv("OPENAI_API_KEY") and os.getenv("ANTHROPIC_API_KEY")
    ):
        return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _openai() -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.4,
        max_tokens=2048,
    )


def _anthropic() -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        temperature=0.4,
        max_tokens=2048,
    )
