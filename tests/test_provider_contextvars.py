"""Concurrent provider_override must not cross-contaminate."""

from __future__ import annotations

import asyncio

import pytest

from agent_lab.invoke import provider
from agent_lab.runner import provider_override


@pytest.mark.fast
def test_concurrent_provider_override_isolated() -> None:
    async def read_provider(expected: str) -> str:
        with provider_override(expected):
            await asyncio.sleep(0.05)
            return provider()

    async def _main() -> tuple[str, str]:
        return await asyncio.gather(
            read_provider("openai"),
            read_provider("anthropic"),
        )

    openai_result, anthropic_result = asyncio.run(_main())
    assert openai_result == "openai"
    assert anthropic_result == "anthropic"
