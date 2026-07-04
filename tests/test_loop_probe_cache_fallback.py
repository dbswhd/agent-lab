from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clear_model_profile_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_lab.model_policy as mp

    before = dict(mp._MODEL_PROFILE_REGISTRY)
    mp._MODEL_PROFILE_REGISTRY.clear()
    mp._MODEL_PROFILE_REGISTRY.update(mp._build_default_registry())
    yield
    mp._MODEL_PROFILE_REGISTRY.clear()
    mp._MODEL_PROFILE_REGISTRY.update(before)


def test_live_probe_failure_falls_back_to_fresh_loop_ready_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.model_policy import model_readiness
    from agent_lab.model_policy_probe import probe_loop_capabilities_cached

    cache_path = tmp_path / "probe.json"
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE_CACHE", str(cache_path))
    probed_at = datetime.now(timezone.utc).isoformat()
    cache_path.write_text(
        f"""
{{
  "kimi_work:k2p6": {{
    "provider": "local",
    "supports_tools": true,
    "supports_inbox_mcp": true,
    "supports_json_envelope": true,
    "supports_long_context": false,
    "cost_tier": "low",
    "latency_tier": "medium",
    "probed_at": "{probed_at}"
  }}
}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def _fail_live_probe(agent_id: str, model_id: str):
        return None

    monkeypatch.setattr(
        "agent_lab.model_policy_probe.probe_loop_capabilities",
        _fail_live_probe,
    )

    from agent_lab.kimi.work_provider import kimi_work_model
    from agent_lab.model_policy import register_model_profile

    mid = kimi_work_model()
    profile = probe_loop_capabilities_cached("kimi_work", mid)
    assert profile is not None
    assert profile.supports_tools is True
    register_model_profile(profile)
    readiness = model_readiness("kimi_work", model_id=mid)
    assert readiness is not None
    assert readiness.loop_ready is True


def test_failed_live_probe_does_not_overwrite_loop_ready_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.model_policy_probe import probe_loop_capabilities_cached

    cache_path = tmp_path / "probe.json"
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE_CACHE", str(cache_path))
    probed_at = datetime.now(timezone.utc).isoformat()
    cache_path.write_text(
        f"""
{{
  "kimi_work:k2p6": {{
    "provider": "local",
    "supports_tools": true,
    "supports_inbox_mcp": true,
    "supports_json_envelope": true,
    "supports_long_context": false,
    "cost_tier": "low",
    "latency_tier": "medium",
    "probed_at": "{probed_at}"
  }}
}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def _fail_live_probe(agent_id: str, model_id: str):
        from agent_lab.model_policy import _substitute_profile

        return _substitute_profile("kimi_work", model_id)

    monkeypatch.setattr(
        "agent_lab.model_policy_probe.probe_loop_capabilities",
        _fail_live_probe,
    )

    from agent_lab.kimi.work_provider import kimi_work_model

    mid = kimi_work_model()
    probe_loop_capabilities_cached("kimi_work", mid)
    saved = cache_path.read_text(encoding="utf-8")
    assert '"supports_tools": true' in saved
    assert '"supports_json_envelope": true' in saved
