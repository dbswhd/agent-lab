"""Mission OS notify SSOT — merge_ready, gate_blocked, adapter egress."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_lab.gateway.notify_helpers import (
    notify_auto_merge_blocked,
    notify_gate_blocked,
    notify_merge_ready,
)


@pytest.fixture
def session_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import agent_lab.session as session_mod

    folder = tmp_path / "notify-sess"
    folder.mkdir()
    (folder / "topic.txt").write_text("notify\n", encoding="utf-8")
    (folder / "run.json").write_text('{"gate_profile":"assistant"}\n', encoding="utf-8")
    monkeypatch.setattr(session_mod, "SESSIONS_DIR", tmp_path)
    return folder


def test_notify_merge_ready_calls_fan_out(session_folder: Path) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(event: str, payload: dict, **kwargs):
        calls.append((event, payload))
        return {"ok": True, "event": event}

    execution = {"id": "exec-1", "status": "pending_approval", "action_index": 0}
    with patch("agent_lab.gateway.adapters.fan_out_gateway_notify", side_effect=_capture):
        result = notify_merge_ready(session_folder, execution)
    assert result["ok"] is True
    assert calls[0][0] == "merge_ready"
    assert calls[0][1]["session_id"] == session_folder.name
    assert calls[0][1]["execution_id"] == "exec-1"
    assert calls[0][1]["gate_profile"] == "assistant"


def test_notify_auto_merge_blocked_calls_fan_out(session_folder: Path) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(event: str, payload: dict, **kwargs):
        calls.append((event, payload))
        return {"ok": True, "event": event}

    execution = {"id": "exec-blocked", "status": "pending_approval", "action_index": 1}
    eligibility = {"eligible": False, "reason": "trust_budget_exhausted"}
    with patch("agent_lab.gateway.adapters.fan_out_gateway_notify", side_effect=_capture):
        result = notify_auto_merge_blocked(
            session_folder,
            execution=execution,
            eligibility=eligibility,
            source="scheduled_tick",
        )
    assert result["ok"] is True
    assert calls[0][0] == "auto_merge_blocked"
    assert calls[0][1]["execution_id"] == "exec-blocked"
    assert calls[0][1]["reason"] == "trust_budget_exhausted"
    assert calls[0][1]["source"] == "scheduled_tick"


def test_notify_auto_merge_blocked_dedupes_per_execution(session_folder: Path) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(event: str, payload: dict, **kwargs):
        calls.append((event, payload))
        return {"ok": True, "event": event}

    execution = {"id": "exec-once", "status": "pending_approval", "action_index": 1}
    eligibility = {"eligible": False, "reason": "classifier_denied"}
    with patch("agent_lab.gateway.adapters.fan_out_gateway_notify", side_effect=_capture):
        first = notify_auto_merge_blocked(
            session_folder,
            execution=execution,
            eligibility=eligibility,
        )
        second = notify_auto_merge_blocked(
            session_folder,
            execution=execution,
            eligibility=eligibility,
        )
    assert first["ok"] is True
    assert second.get("skipped") is True
    assert second.get("reason") == "already_notified"
    assert len(calls) == 1


def test_notify_gate_blocked_calls_fan_out(session_folder: Path) -> None:
    calls: list[tuple[str, dict]] = []

    def _capture(event: str, payload: dict, **kwargs):
        calls.append((event, payload))
        return {"ok": True, "event": event}

    snap = {
        "block_source": "execute",
        "block_reason": "pending_build",
        "next_allowed_action": "resolve_inbox",
        "gates": {"gate_profile": "dev"},
    }
    with patch("agent_lab.gateway.adapters.fan_out_gateway_notify", side_effect=_capture):
        notify_gate_blocked(session_folder, snap, source="test")
    assert calls[0][0] == "gate_blocked"
    assert calls[0][1]["block_reason"] == "pending_build"
    assert calls[0][1]["source"] == "test"


def test_telegram_adapter_handles_merge_ready() -> None:
    from agent_lab.gateway.adapters_telegram import TelegramGatewayAdapter

    adapter = TelegramGatewayAdapter()
    with patch(
        "agent_lab.gateway.telegram_adapter._notify_telegram_text",
        return_value={"ok": True},
    ) as mock:
        result = adapter.notify(
            "merge_ready",
            {"session_id": "s1", "execution_id": "e1", "gate_profile": "assistant"},
        )
    assert result["ok"] is True
    mock.assert_called_once()


def test_telegram_adapter_handles_auto_merge_blocked() -> None:
    from agent_lab.gateway.adapters_telegram import TelegramGatewayAdapter

    adapter = TelegramGatewayAdapter()
    with patch(
        "agent_lab.gateway.telegram_adapter._notify_telegram_text",
        return_value={"ok": True},
    ) as mock:
        result = adapter.notify(
            "auto_merge_blocked",
            {
                "session_id": "s1",
                "execution_id": "e1",
                "gate_profile": "assistant",
                "reason": "trust_budget_exhausted",
            },
        )
    assert result["ok"] is True
    mock.assert_called_once()
    assert "trust_budget_exhausted" in mock.call_args[0][0]


def test_discord_adapter_skips_unknown_event() -> None:
    from agent_lab.gateway.adapters_discord import DiscordGatewayAdapter

    adapter = DiscordGatewayAdapter()
    result = adapter.notify("unknown_event", {"session_id": "s1"})
    assert result.get("skipped") is True


def test_execute_lane_notifies_gate_blocked(session_folder: Path) -> None:
    from agent_lab.runtime.execute_lane import handle_execute_dry_run_start

    blocked_snap = {
        "block_source": "execute",
        "block_reason": "pending_build",
        "gates": {"execute": {"open": False}},
    }
    calls: list[str] = []
    with (
        patch(
            "agent_lab.runtime.policy.PolicyEngine.gate_snapshot",
            return_value=blocked_snap,
        ),
        patch(
            "agent_lab.gateway.notify_helpers.notify_gate_blocked",
            side_effect=lambda *a, **k: calls.append("blocked") or {"ok": True},
        ),
    ):
        result = handle_execute_dry_run_start(session_folder, {"action_index": 0})
    assert result.skipped is True
    assert calls == ["blocked"]


def test_scheduled_merge_review_notifies_auto_merge_blocked(
    session_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_lab.mission.loop import enable_mission_loop
    from agent_lab.mission.advance import maybe_advance_mission
    from agent_lab.run.meta import patch_run_meta

    enable_mission_loop(session_folder)
    patch_run_meta(
        session_folder,
        lambda run: {
            **run,
            "gate_profile": "assistant",
            "trust_budget": {"auto_merge_remaining": 0},
            "executions": [
                {
                    "id": "exec-mr",
                    "status": "pending_approval",
                    "action_index": 1,
                    "source_touched_paths": ["docs/README.md"],
                }
            ],
            "mission_loop": {
                "enabled": True,
                "phase": "MERGE_REVIEW",
                "current_action_index": 1,
                "last_execution_id": "exec-mr",
            },
        },
    )

    calls: list[str] = []
    monkeypatch.setattr(
        "agent_lab.gateway.notify_helpers.notify_auto_merge_blocked",
        lambda *a, **k: calls.append("blocked") or {"ok": True},
    )

    out = maybe_advance_mission(session_folder, scheduled=True)
    assert out.get("reason") == "auto_merge_not_eligible"
    assert out.get("notify", {}).get("ok") is True
    assert calls == ["blocked"]
