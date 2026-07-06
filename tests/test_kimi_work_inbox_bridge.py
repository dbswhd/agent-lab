from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from agent_lab.human_inbox import resolve_inbox_item
from agent_lab.run.meta import read_run_meta


@pytest.fixture(autouse=True)
def _mock_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")


def test_inbox_bridge_executes_ask_human_mock(tmp_path: Path) -> None:
    from agent_lab.kimi import work_provider as kwp

    folder = tmp_path / "sess"
    folder.mkdir()
    (folder / "run.json").write_text('{"human_inbox": [], "team_lead": "kimi_work"}', encoding="utf-8")

    def _resolve() -> None:
        time.sleep(0.05)
        run = read_run_meta(folder)
        pending = [i for i in run.get("human_inbox", []) if i.get("status") == "pending"]
        assert len(pending) == 1
        resolve_inbox_item(folder, pending[0]["id"], selected=["narrow"], append_chat=False)

    threading.Thread(target=_resolve, daemon=True).start()
    text = kwp.respond(
        "sys",
        "[mock-inbox-ask] pick scope",
        session_folder=folder,
        inbox_mcp=True,
    )
    assert "Inbox resolved" in text
    assert read_run_meta(folder).get("human_inbox")


def test_inbox_bridge_adds_system_addon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.kimi import work_provider as kwp

    folder = tmp_path / "sess2"
    folder.mkdir()
    (folder / "run.json").write_text('{"human_inbox": [], "team_lead": "kimi_work"}', encoding="utf-8")

    captured: dict[str, str] = {}

    def _fake_send_turn(**kwargs: object) -> str:
        captured["system"] = str(kwargs.get("system") or "")
        return "ok"

    monkeypatch.setattr(kwp, "send_turn", _fake_send_turn)
    kwp.respond("base", "hi", session_folder=folder, inbox_mcp=True)
    assert "Human Inbox" in captured.get("system", "")


def test_kimi_work_loop_phase2_requires_inbox_capability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.model_policy import loop_readiness_failure, model_readiness
    from agent_lab.model_policy_probe import probe_loop_capabilities_cached

    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE", "1")
    monkeypatch.setenv("AGENT_LAB_LOOP_PROBE_CACHE", str(tmp_path / "probe.json"))
    monkeypatch.setenv("AGENT_LAB_KIMI_WORK_LOOP_PHASE", "2")

    profile = probe_loop_capabilities_cached("kimi_work", "k2p6")
    assert profile is not None
    assert profile.supports_inbox_mcp is True
    readiness = model_readiness("kimi_work")
    assert readiness is not None
    assert readiness.loop_ready is True
    assert loop_readiness_failure(["kimi_work"]) is None


def test_normalize_inbox_tool_names() -> None:
    from agent_lab.kimi.work_inbox_bridge import _normalize_tool_name

    assert _normalize_tool_name("inbox.askHuman") == "ask_human"
    assert _normalize_tool_name("inbox.proposeBuild") == "propose_build"


def test_inbox_bridge_logs_unrecognized_inbox_tool_call() -> None:
    from agent_lab.kimi.work_inbox_bridge import KimiWorkInboxBridge

    activity: list[str] = []
    bridge = KimiWorkInboxBridge(
        session_folder=Path("/tmp/unused"),
        conversation_key="conv-1",
        on_activity=activity.append,
    )
    handled = bridge._try_handle(
        "conversations.message.snapshot",
        {
            "parts": [
                {
                    "kind": "tool-call",
                    "toolCallId": "tc-1",
                    "toolName": "inbox.askHumanBroken",
                    "args": "{}",
                }
            ]
        },
        lambda _method, _payload: None,
    )
    assert handled is False
    assert any("[inbox · expected ask_human]" in line for line in activity)
