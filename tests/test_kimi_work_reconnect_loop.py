from __future__ import annotations

import pytest


def test_resolve_runtime_model_id_uses_kimi_work_provider() -> None:
    from agent_lab.kimi.work_provider import kimi_work_model
    from agent_lab.model_policy import resolve_runtime_model_id

    assert resolve_runtime_model_id("kimi_work") == kimi_work_model()


def test_reconnect_kimi_work_reprobes_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.agent import health as health_mod
    from agent_lab.kimi.work_provider import kimi_work_model
    from agent_lab.model_policy import ModelReadiness

    calls: list[tuple[str, str]] = []
    mid = kimi_work_model()

    monkeypatch.setattr(
        "agent_lab.kimi.control_client.invalidate_endpoint_cache",
        lambda: None,
    )
    monkeypatch.setattr(
        "agent_lab.kimi.daimon_supervisor.ensure_daimon",
        lambda spawn_only=False: "ws://mock",
    )
    monkeypatch.setattr(
        "agent_lab.kimi.daimon_supervisor.shutdown_owned_daimon",
        lambda: None,
    )
    monkeypatch.setattr(
        "agent_lab.kimi.control_client.probe_endpoint_ws",
        lambda _endpoint: True,
    )
    monkeypatch.setattr(
        "agent_lab.model_policy.invalidate_model_profile",
        lambda agent_id, *, model_id=None: None,
    )
    monkeypatch.setattr(
        "agent_lab.model_policy_probe.invalidate_loop_probe_cache",
        lambda agent_id, *, model_id=None: None,
    )
    monkeypatch.setattr(
        "agent_lab.model_policy_probe.clear_kimi_work_loop_probe_session",
        lambda: None,
    )

    def _probe(agent_id: str, model_id: str):
        calls.append((agent_id, model_id))
        from agent_lab.model_policy import _substitute_profile

        return _substitute_profile("kimi_work", model_id)

    monkeypatch.setattr(
        "agent_lab.model_policy_probe.probe_loop_capabilities_cached",
        _probe,
    )
    monkeypatch.setattr(
        health_mod,
        "agent_health_row",
        lambda *_args, **_kwargs: {
            "id": "kimi_work",
            "ready": True,
            "bridge": "ok",
            "loop_ready": True,
        },
    )
    monkeypatch.setattr(
        "agent_lab.model_policy.model_readiness",
        lambda *_args, **_kwargs: ModelReadiness(
            provider="local",
            model_id=mid,
            team_ready=True,
            loop_ready=True,
            loop_blockers=(),
        ),
    )

    payload = health_mod.reconnect_kimi_work_bridge()

    assert calls == [("kimi_work", mid)]
    assert payload["bridge"] == "ok"
    assert payload["loop_ready"] is True
