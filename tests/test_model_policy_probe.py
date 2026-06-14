from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

from agent_lab.model_policy_probe import (
    loop_probe_enabled,
    probe_loop_capabilities,
    probe_loop_capabilities_cached,
)


def test_probe_loop_capabilities_mock_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    profile = probe_loop_capabilities("cursor", "oss-local")
    assert profile is not None
    assert profile.supports_tools is True
    assert profile.supports_inbox_mcp is True
    assert profile.supports_json_envelope is True


def test_probe_cached_registers_unknown_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.model_policy import model_readiness

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE_CACHE", str(tmp_path / "probe.json"))
    monkeypatch.setenv("CURSOR_MODEL", "oss-probed")

    profile = probe_loop_capabilities_cached("cursor", "oss-probed")
    assert profile is not None
    readiness = model_readiness("cursor")
    assert readiness is not None
    assert readiness.loop_ready is True


def test_loop_probe_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
    assert loop_probe_enabled() is False
