from __future__ import annotations

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


def test_loop_readiness_failure_detail_includes_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.model_policy import loop_readiness_failure_detail

    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "0")
    detail = loop_readiness_failure_detail(["kimi_work"])
    assert detail is not None
    assert detail["code"] == "loop_readiness_failed"
    assert detail["agents"] == ["kimi_work"]
    rows = detail["agent_details"]
    assert len(rows) == 1
    assert rows[0]["id"] == "kimi_work"
    assert rows[0]["loop_ready"] is False
    assert "supports_tools" in rows[0]["loop_blockers"]
    assert rows[0]["blocker_labels"]
    assert "missing:" in str(rows[0]["summary"])
    assert detail["hint"]
