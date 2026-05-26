import os

from langchain_core.messages import HumanMessage, SystemMessage

from agent_lab.agents.prompts import CLAUDE_ROOM


def is_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def respond(system: str, user: str) -> str:
    from langchain_anthropic import ChatAnthropic

    llm = ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        temperature=0.4,
        max_tokens=2048,
    )
    msg = llm.invoke(
        [
            SystemMessage(content=system or CLAUDE_ROOM),
            HumanMessage(content=user),
        ]
    )
    return (msg.content or "").strip()
