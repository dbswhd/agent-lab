"""P2 integration: kimi_work provider tools + registry mock routing."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_share(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("agent_lab.app_config.config_dir", lambda: tmp_path)
    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path / "share"))
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")


def test_provider_mock_tools_via_mapper(tmp_path: Path) -> None:
    from agent_lab.kimi import work_provider as kwp

    events: list[tuple[str, dict]] = []

    def on_bridge(kind: str, data: dict) -> None:
        events.append((kind, data))

    text = kwp.respond(
        "sys",
        "[mock-tools] probe",
        session_folder=tmp_path,
        on_bridge_event=on_bridge,
    )
    assert text == "Tool turn complete."
    kinds = [k for k, _ in events]
    assert "tool_start" in kinds
    assert "tool_output" in kinds
    assert "tool_done" in kinds


def test_registry_routes_kimi_work_mock_with_session_folder(tmp_path: Path) -> None:
    from agent_lab.agents import registry

    events: list[str] = []

    def on_bridge(kind: str, data: dict) -> None:
        events.append(kind)

    reply = registry.call_agent_reply(
        "kimi_work",
        "sys",
        "[mock-tools] via registry",
        session_folder=tmp_path,
        on_bridge_event=on_bridge,
    )
    assert reply.text == "Tool turn complete."
    assert "tool_start" in events


def test_registry_generic_mock_without_session_folder() -> None:
    from agent_lab.agents import registry

    reply = registry.call_agent_reply("kimi_work", "sys", "ping")
    assert "[mock:Kimi Work]" in reply.text
