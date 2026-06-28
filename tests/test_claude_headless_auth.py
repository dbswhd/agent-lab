"""Claude OAuth status vs headless ``-p`` probe (send gate + invoke preflight)."""

from __future__ import annotations

import time

import pytest

from agent_lab.agent.preflight import agent_preflight_row


def test_agent_preflight_claude_runs_headless_probe_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_CLAUDE_SKIP_HEADLESS_PROBE", raising=False)
    probes: list[dict[str, object]] = []

    monkeypatch.setattr(
        "agent_lab.claude.cli.resolve_claude_bin",
        lambda: "/tmp/claude",
    )
    monkeypatch.setattr(
        "agent_lab.claude.cli.claude_auth_logged_in",
        lambda **kw: (True, None),
    )

    def _probe(**kw):
        probes.append(kw)
        return True, None

    monkeypatch.setattr("agent_lab.claude.cli.probe_auth", _probe)
    monkeypatch.setattr(
        "agent_lab.agent.preflight._probe_cli_version",
        lambda *_args, **_kwargs: (True, "2.1.50"),
    )

    row = agent_preflight_row("claude", probe_cli=True)

    assert row["ready"] is True
    assert probes
    assert probes[0].get("use_cache") is True


def test_agent_preflight_claude_headless_probe_failure(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_CLAUDE_SKIP_HEADLESS_PROBE", raising=False)
    monkeypatch.setattr(
        "agent_lab.claude.cli.resolve_claude_bin",
        lambda: "/tmp/claude",
    )
    monkeypatch.setattr(
        "agent_lab.claude.cli.claude_auth_logged_in",
        lambda **kw: (True, None),
    )
    monkeypatch.setattr(
        "agent_lab.claude.cli.probe_auth",
        lambda **kw: (False, "401 Invalid authentication credentials"),
    )
    monkeypatch.setattr(
        "agent_lab.agent.preflight._probe_cli_version",
        lambda *_args, **_kwargs: (True, "2.1.50"),
    )

    row = agent_preflight_row("claude", probe_cli=True)

    assert row["ready"] is False
    assert row["failure_code"] == "claude_auth_failed"
    assert row.get("remediation")


def test_ensure_claude_headless_ready_raises_on_probe_failure(monkeypatch) -> None:
    from agent_lab.claude.cli import ensure_claude_headless_ready

    monkeypatch.delenv("AGENT_LAB_CLAUDE_SKIP_HEADLESS_PROBE", raising=False)
    monkeypatch.setattr(
        "agent_lab.claude.cli.probe_auth",
        lambda **kw: (False, "401 Invalid authentication credentials"),
    )

    with pytest.raises(RuntimeError, match="401"):
        ensure_claude_headless_ready(use_cache=False)


def test_collect_parallel_futures_returns_quickly_on_cancel() -> None:
    from concurrent.futures import ThreadPoolExecutor

    from agent_lab.room.parallel_rounds import _collect_parallel_futures
    from agent_lab.run.control import RoomRunCancelled, clear_cancel, request_cancel

    clear_cancel()
    executor = ThreadPoolExecutor(max_workers=1)
    futures = {executor.submit(lambda: "ok")}
    request_cancel()
    t0 = time.monotonic()
    with pytest.raises(RoomRunCancelled):
        _collect_parallel_futures(executor, futures)
    assert time.monotonic() - t0 < 1.0
    clear_cancel()
