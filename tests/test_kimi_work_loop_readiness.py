from __future__ import annotations

from pathlib import Path

import pytest

from agent_lab.model_policy import loop_blockers, loop_readiness_failure, model_readiness
from agent_lab.model_policy_probe import probe_loop_capabilities, probe_loop_capabilities_cached


@pytest.fixture(autouse=True)
def _clear_model_profile_registry(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_kimi_work_respond_honors_structured_envelope_mock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.kimi import work_provider as kwp

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    text = kwp.respond(
        "sys",
        "hello",
        session_folder=tmp_path,
        request_structured_envelope=True,
    )
    assert text.lstrip().startswith('{"act":')


def test_loop_blockers_waives_inbox_for_kimi_work_phase1(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    from agent_lab.model_policy import _substitute_profile

    monkeypatch.setenv("AGENT_LAB_KIMI_WORK_LOOP_PHASE", "1")
    profile = replace(
        _substitute_profile("kimi_work", "k2p6"),
        supports_tools=True,
        supports_inbox_mcp=False,
        supports_json_envelope=True,
    )
    assert loop_blockers(profile) == ()


def test_loop_blockers_requires_inbox_for_kimi_work_phase2(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    from agent_lab.model_policy import _substitute_profile

    monkeypatch.setenv("AGENT_LAB_KIMI_WORK_LOOP_PHASE", "2")
    profile = replace(
        _substitute_profile("kimi_work", "k2p6"),
        supports_tools=True,
        supports_inbox_mcp=False,
        supports_json_envelope=True,
    )
    assert loop_blockers(profile) == ("supports_inbox_mcp",)


def test_probe_kimi_work_split_capabilities_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
    monkeypatch.setenv("AGENT_LAB_KIMI_WORK_LOOP_PHASE", "2")

    profile = probe_loop_capabilities("kimi_work", "k2p6")
    assert profile is not None
    assert profile.supports_tools is True
    assert profile.supports_json_envelope is True
    assert profile.supports_inbox_mcp is True


def test_kimi_work_loop_ready_phase1_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
    monkeypatch.setenv("AGENT_LAB_KIMI_WORK_LOOP_PHASE", "1")

    readiness = model_readiness("kimi_work")
    assert readiness is not None
    assert readiness.loop_ready is True
    assert loop_readiness_failure(["kimi_work"]) is None


def test_probe_kimi_work_cached_registers_loop_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE_CACHE", str(tmp_path / "probe.json"))
    monkeypatch.setenv("AGENT_LAB_KIMI_WORK_LOOP_PHASE", "1")

    profile = probe_loop_capabilities_cached("kimi_work", "k2p6")
    assert profile is not None
    readiness = model_readiness("kimi_work")
    assert readiness is not None
    assert readiness.loop_ready is True


def test_kimi_work_tool_features_contract() -> None:
    from agent_lab.kimi.work_loop import kimi_work_loop_tool_features_ok

    assert kimi_work_loop_tool_features_ok(
        [
            "conversations.create",
            "conversations.send",
            "workspace.openProject",
        ]
    )
    assert kimi_work_loop_tool_features_ok(
        [
            "capabilities.get",
            "conversations.create",
            "conversations.send",
            "workspace.openProject",
        ]
    )
    assert not kimi_work_loop_tool_features_ok(["conversations.send"])


def test_kimi_work_tool_features_ok_for_daimon_advertised_list() -> None:
    from agent_lab.kimi.work_loop import kimi_work_loop_tool_features_ok

    daimon_features = [
        "conversations.create",
        "conversations.send",
        "workspace.openProject",
        "workspace.listProjects",
        "runtime.status",
    ]
    assert kimi_work_loop_tool_features_ok(daimon_features)


def test_probe_kimi_work_tools_accepts_daimon_feature_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.model_policy_probe import _probe_kimi_work_tools

    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)

    def _fake_rpc(method: str, params: dict[str, object]) -> dict[str, object]:
        assert method == "capabilities.get"
        return {
            "features": [
                "conversations.create",
                "conversations.send",
                "workspace.openProject",
            ]
        }

    monkeypatch.setattr(
        "agent_lab.kimi.work_provider.is_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_lab.kimi.control_client.probe_control",
        lambda: ("ok", None),
    )
    monkeypatch.setattr("agent_lab.kimi.control_client.rpc", _fake_rpc)
    assert _probe_kimi_work_tools() is True


def test_is_usable_conversation_key_mock_only_in_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.kimi.work_session import is_usable_conversation_key

    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    assert is_usable_conversation_key("mock-conv-loop-probe") is False
    assert is_usable_conversation_key("main:conversation:abc-123") is True

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    assert is_usable_conversation_key("mock-conv-loop-probe") is True


def test_ensure_kimi_work_session_drops_stale_mock_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.kimi.work_session import ensure_kimi_work_session, write_state

    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    write_state(
        tmp_path,
        {
            "workspacePath": str(tmp_path),
            "conversationKey": "mock-conv-loop-probe",
        },
    )

    created: list[str] = []

    def _fake_rpc(method: str, params: dict[str, object]) -> dict[str, str]:
        if method == "workspace.openProject":
            return {"status": "opened"}
        if method == "conversations.create":
            key = "main:conversation:probe-123"
            created.append(key)
            return {"conversationKey": key}
        raise AssertionError(method)

    monkeypatch.setattr("agent_lab.kimi.control_client.rpc", _fake_rpc)
    monkeypatch.setattr("agent_lab.kimi.control_client.rpc_batch", lambda calls: [_fake_rpc(m, p) for m, p in calls])

    key = ensure_kimi_work_session(tmp_path, workspace_path=tmp_path, title="loop-probe")
    assert key == "main:conversation:probe-123"
    assert created == ["main:conversation:probe-123"]


def test_probe_kimi_work_envelope_validates_speech_act(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.model_policy_probe import _probe_substitute_envelope

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    assert _probe_substitute_envelope("kimi_work", "k2p6") is True


def test_probe_kimi_work_envelope_rejects_invalid_act(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.kimi import work_provider as kwp
    from agent_lab.model_policy_probe import _probe_substitute_envelope

    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")

    def _bad_reply(**kwargs: object) -> str:
        return '{"status":"ok"}'

    monkeypatch.setattr(kwp, "send_turn", _bad_reply)
    assert _probe_substitute_envelope("kimi_work", "k2p6") is False


def test_kimi_work_envelope_strict_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.kimi.work_loop import kimi_work_envelope_strict

    monkeypatch.delenv("AGENT_LAB_KIMI_WORK_ENVELOPE_STRICT", raising=False)
    assert kimi_work_envelope_strict() is False
    monkeypatch.setenv("AGENT_LAB_KIMI_WORK_ENVELOPE_STRICT", "1")
    assert kimi_work_envelope_strict() is True


def test_kimi_work_envelope_skips_live_probe_when_not_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_lab.model_policy_probe import _probe_substitute_loop_flags

    monkeypatch.delenv("AGENT_LAB_KIMI_WORK_ENVELOPE_STRICT", raising=False)
    monkeypatch.setattr(
        "agent_lab.model_policy_probe._probe_kimi_work_tools",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_lab.model_policy_probe._probe_kimi_work_inbox",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent_lab.model_policy_probe._probe_substitute_envelope",
        lambda *_args, **_kwargs: False,
    )

    tools, inbox, envelope = _probe_substitute_loop_flags("kimi_work", "k2p6")
    assert tools is True
    assert inbox is True
    assert envelope is True
