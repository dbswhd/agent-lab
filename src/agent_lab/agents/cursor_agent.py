import os
from pathlib import Path
from typing import Any

from agent_lab.agent_permissions import permission_preamble


def _sdk_installed() -> bool:
    try:
        import cursor_sdk  # noqa: F401

        return True
    except ImportError:
        return False


def is_available() -> bool:
    return bool(os.getenv("CURSOR_API_KEY", "").strip()) and _sdk_installed()


def _resolve_cwd(permissions: dict[str, Any] | None) -> str:
    home = Path.home()
    if permissions:
        p = permissions.get("cursor") or {}
        if p.get("local_pipeline"):
            pipeline = os.getenv(
                "QUANT_PIPELINE_ROOT",
                str(home / "Projects" / "quant-pipeline"),
            )
            if Path(pipeline).is_dir():
                return pipeline
        if p.get("local_agent_lab"):
            root = os.getenv("AGENT_LAB_ROOT")
            if root and Path(root).is_dir():
                return root
    return (
        os.getenv("CODEX_CWD")
        or os.getenv("AGENT_LAB_ROOT")
        or str(Path(__file__).resolve().parents[3])
    )


def respond(
    system: str,
    user: str,
    *,
    permissions: dict[str, Any] | None = None,
) -> str:
    from agent_lab.agents.prompts import CURSOR_ROOM

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CURSOR_API_KEY not set")

    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
    except ImportError as e:
        raise RuntimeError(
            "Install cursor-sdk: pip install cursor-sdk"
        ) from e

    extra = permission_preamble(permissions, "cursor")
    prompt_parts = [system or CURSOR_ROOM]
    if extra:
        prompt_parts.append(extra)
    prompt_parts.append(f"\n---\n\n{user}")
    prompt = "\n\n".join(prompt_parts)

    cwd = _resolve_cwd(permissions)
    result = Agent.prompt(
        prompt,
        AgentOptions(
            api_key=api_key,
            model=os.getenv("CURSOR_MODEL", "composer-2.5"),
            local=LocalAgentOptions(cwd=cwd),
        ),
    )
    text = getattr(result, "result", None) or getattr(result, "output", None)
    if text:
        return str(text).strip()
    return str(result).strip()
