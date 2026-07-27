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


def _reset_probe_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """probe_auth short-circuits under AGENT_LAB_MOCK_AGENTS and reads
    module-level cache globals — both need resetting to exercise the real
    subprocess-facing body in isolation."""
    import agent_lab.claude.cli as claude_cli

    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    monkeypatch.delenv("AGENT_LAB_CLAUDE_SKIP_HEADLESS_PROBE", raising=False)
    monkeypatch.delenv("CLAUDE_SKIP_AUTH_PROBE", raising=False)
    monkeypatch.setattr(claude_cli, "_AUTH_PROBE_CACHE", None)
    monkeypatch.setattr(claude_cli, "_AUTH_STATUS_CACHE", None)
    monkeypatch.setattr(claude_cli, "resolve_claude_bin", lambda: "/tmp/claude")
    monkeypatch.setattr(claude_cli, "claude_auth_logged_in", lambda **kw: (True, None))
    monkeypatch.setattr(claude_cli, "retry_base_delay_sec", lambda: 0.0)  # no real sleep in tests


def test_probe_auth_retries_transient_timeout_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single subprocess timeout must not fail the probe outright — the
    retry (mirroring the real invoke path's retry_call/is_retryable policy)
    should recover on the second attempt."""
    import subprocess

    import agent_lab.claude.cli as claude_cli

    _reset_probe_state(monkeypatch)
    calls = {"n": 0}

    def _fake_run(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 1)
        return subprocess.CompletedProcess(cmd, 0, stdout="AUTH_OK", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    ok, detail = claude_cli.probe_auth(use_cache=False)

    assert ok is True
    assert detail is None
    assert calls["n"] == 2  # first attempt timed out, retry succeeded
    assert claude_cli._AUTH_PROBE_CACHE is not None
    assert claude_cli._AUTH_PROBE_CACHE[1] is True


def test_probe_auth_caches_genuine_auth_failure_with_long_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real 401 is not retryable (is_retryable excludes auth text) and must
    keep the full 5-minute negative-cache TTL — retrying a revoked token
    can't help, and this TTL also throttles how often the probe re-hits the
    Anthropic API for a condition only the user (re-login) can fix."""
    import subprocess

    import agent_lab.claude.cli as claude_cli

    _reset_probe_state(monkeypatch)
    calls = {"n": 0}

    def _fake_run(cmd, **kwargs):
        calls["n"] += 1
        return subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="ERROR: 401 Invalid authentication credentials"
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    ok, detail = claude_cli.probe_auth(use_cache=False)

    assert ok is False
    assert "401" in (detail or "")
    assert calls["n"] == 1  # non-retryable — no second attempt burned on a dead token
    assert claude_cli._AUTH_PROBE_CACHE is not None
    assert claude_cli._AUTH_PROBE_CACHE[3] == claude_cli._AUTH_PROBE_TTL_SEC


def test_probe_auth_caches_persistent_transient_failure_with_short_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure that still doesn't look auth-related even after the retry
    (e.g. a network blip that outlasted both attempts) must NOT be pinned for
    the full 5 minutes — a short TTL lets the room re-check soon instead of
    reporting Claude unready long after the blip has passed."""
    import subprocess

    import agent_lab.claude.cli as claude_cli

    _reset_probe_state(monkeypatch)

    def _fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 1)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    ok, detail = claude_cli.probe_auth(use_cache=False)

    assert ok is False
    assert "timed out" in (detail or "")
    assert claude_cli._AUTH_PROBE_CACHE is not None
    assert claude_cli._AUTH_PROBE_CACHE[3] == claude_cli._AUTH_PROBE_TRANSIENT_TTL_SEC


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
    from agent_lab.run.control import clear_cancel, is_cancelled, request_cancel

    clear_cancel()
    executor = ThreadPoolExecutor(max_workers=1)
    futures = {executor.submit(lambda: "ok")}
    request_cancel()
    t0 = time.monotonic()
    _collect_parallel_futures(executor, futures)
    assert time.monotonic() - t0 < 1.0
    assert is_cancelled()
    clear_cancel()


def test_collect_parallel_futures_waits_for_partial_on_cancel() -> None:
    import threading

    from concurrent.futures import ThreadPoolExecutor

    from agent_lab.room.messages import ChatMessage
    from agent_lab.room.parallel_rounds import _collect_parallel_futures
    from agent_lab.run.control import clear_cancel, is_cancelled, request_cancel

    clear_cancel()
    partial = ChatMessage(
        role="agent",
        agent="claude",
        content="partial analysis\n\n_(취소됨)_",
        parallel_round=2,
    )

    def slow_agent() -> ChatMessage:
        time.sleep(1.0)
        return partial

    executor = ThreadPoolExecutor(max_workers=1)
    futures = {executor.submit(slow_agent)}

    def cancel_soon() -> None:
        time.sleep(0.15)
        request_cancel()

    threading.Thread(target=cancel_soon, daemon=True).start()
    results = _collect_parallel_futures(executor, futures)
    assert len(results) == 1
    assert results[0].content == partial.content
    assert is_cancelled()
    clear_cancel()
