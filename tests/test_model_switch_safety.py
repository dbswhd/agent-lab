from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from agent_lab.model_policy import (
    SUBSTITUTE_AGENT_IDS,
    _substitute_agent_id,
    _substitute_profile,
    loop_readiness_failure,
    model_profile_for,
    model_readiness,
)
from agent_lab.model_policy_probe import (
    _live_probe_enabled,
    probe_loop_capabilities,
    probe_loop_capabilities_cached,
)


@pytest.fixture(autouse=True)
def _clear_model_profile_registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate the global profile registry from cross-test pollution.

    Start each test from the clean default registry (not whatever a prior test in the same
    xdist worker registered for kimi/local via probe/eval-load), and block lazy loop-eval
    loading so substitute conservative behavior is deterministic. Restore afterwards.
    """
    import agent_lab.model_policy as mp

    before = dict(mp._MODEL_PROFILE_REGISTRY)
    before_loaded = mp._LOOP_EVAL_LOADED
    mp._MODEL_PROFILE_REGISTRY.clear()
    mp._MODEL_PROFILE_REGISTRY.update(mp._build_default_registry())
    mp._LOOP_EVAL_LOADED = True
    yield
    mp._MODEL_PROFILE_REGISTRY.clear()
    mp._MODEL_PROFILE_REGISTRY.update(before)
    mp._LOOP_EVAL_LOADED = before_loaded


class TestSubstituteRecognition:
    def test_substitute_agent_ids_frozen_set(self) -> None:
        assert SUBSTITUTE_AGENT_IDS == {"kimi", "kimi_work", "local"}

    def test_known_agent_id_rejects_substitutes(self) -> None:
        from agent_lab.model_policy import _known_agent_id

        assert _known_agent_id("kimi") is None
        assert _known_agent_id("local") is None
        assert _known_agent_id("kimi_work") is None

    def test_substitute_agent_id_recognises_all(self) -> None:
        assert _substitute_agent_id("kimi") == "kimi"
        assert _substitute_agent_id("kimi_work") == "kimi_work"
        assert _substitute_agent_id("local") == "local"
        assert _substitute_agent_id("cursor") is None
        assert _substitute_agent_id("unknown") is None

    def test_substitute_profile_is_not_loop_ready(self) -> None:
        profile = _substitute_profile("kimi", "kimi-default")
        assert profile.agent == "kimi"
        assert profile.supports_tools is False
        assert profile.supports_inbox_mcp is False
        assert profile.supports_json_envelope is False
        assert profile.cost_tier == "low"


class TestFailClosedOnUnknown:
    def test_loop_readiness_failure_blocks_unknown_agents(self) -> None:
        """Unknown agents (not recognised by _known_agent_id or _substitute_agent_id)
        must fail-closed, not be silently skipped."""
        failure = loop_readiness_failure(["totally_unknown_agent"])
        assert failure is not None
        assert "totally_unknown_agent" in failure.agents
        assert "not recognised" in failure.reason

    def test_loop_readiness_failure_blocks_substitutes_without_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Substitutes without a passing live probe must be not-loop-ready."""
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
        failure = loop_readiness_failure(["kimi", "local"])
        assert failure is not None
        assert "kimi" in failure.agents
        assert "local" in failure.agents
        assert "lacks question/tool capability" in failure.reason

    def test_loop_readiness_failure_allows_known_defaults(self) -> None:
        """Built-in agents with default profiles should still pass."""
        assert loop_readiness_failure(["cursor", "codex", "claude"]) is None


class TestTwoStageProbe:
    def test_live_probe_flag_default_off(self) -> None:
        assert _live_probe_enabled() is False

    def test_live_probe_flag_can_be_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE_LIVE", "1")
        assert _live_probe_enabled() is True

    def test_probe_loop_capabilities_substitute_conservative_when_probe_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
        monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "0")
        profile = probe_loop_capabilities("kimi", "kimi-default")
        assert profile is not None
        assert profile.supports_tools is False
        assert profile.supports_json_envelope is False

    def test_probe_loop_capabilities_substitute_mock_live_upgrade(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When mock agents are on, live probe succeeds and substitutes earn loop-readiness."""
        monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
        # Live probe is always attempted for substitutes; mock mode makes it succeed.
        profile = probe_loop_capabilities("kimi", "kimi-default")
        assert profile is not None
        assert profile.supports_tools is True
        assert profile.supports_inbox_mcp is True
        assert profile.supports_json_envelope is True

    def test_probe_loop_capabilities_builtin_no_live_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Built-in agents (cursor/codex/claude) only run live probe when flag is on."""
        monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE_LIVE", "0")
        profile = probe_loop_capabilities("cursor", "cursor-default")
        assert profile is not None
        # Mock mode makes infra probe succeed, and live probe is off for built-ins.
        assert profile.supports_tools is True

    def test_probe_loop_capabilities_cached_handles_substitute(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE_CACHE", str(tmp_path / "probe.json"))
        profile = probe_loop_capabilities_cached("local", "local-default")
        assert profile is not None
        assert profile.agent == "local"
        # Mock mode → live probe succeeds → upgraded to loop-ready.
        assert profile.supports_tools is True

    def test_model_profile_for_substitute_returns_conservative_when_no_probe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
        profile = model_profile_for("kimi")
        assert profile is not None
        assert profile.supports_tools is False
        readiness = model_readiness("kimi")
        assert readiness is not None
        assert readiness.loop_ready is False

    def test_model_profile_for_substitute_mock_upgrade(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
        profile = model_profile_for("kimi")
        assert profile is not None
        assert profile.supports_tools is True
        readiness = model_readiness("kimi")
        assert readiness is not None
        assert readiness.loop_ready is True

    def test_loop_readiness_failure_allows_upgraded_substitute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A substitute that passes the live probe should be loop-ready."""
        monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
        assert loop_readiness_failure(["kimi"]) is None

    def test_loop_readiness_failure_mixed_known_and_substitute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mix of known (ready) and substitute (not ready) should fail on substitutes."""
        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
        failure = loop_readiness_failure(["cursor", "kimi"])
        assert failure is not None
        assert "kimi" in failure.agents
        assert "cursor" not in failure.agents

    def test_partition_loop_capable_agents_keeps_ready_primary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from agent_lab.model_policy import partition_loop_capable_agents

        monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
        capable, skipped = partition_loop_capable_agents(["claude", "kimi_work"])
        assert capable == ("claude",)
        assert skipped == ("kimi_work",)
