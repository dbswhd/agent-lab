from __future__ import annotations

import pytest

from agent_lab.cli_retry import is_retryable, retry_call


def test_is_retryable_whitelist_and_exclusions():
    assert is_retryable("ERROR 429: rate limit")
    assert is_retryable("request timed out after 120s")
    assert is_retryable("connection refused")
    assert is_retryable("temporarily unavailable")
    assert is_retryable("model overloaded")
    assert is_retryable("codex exec failed (exit 52)")

    assert not is_retryable("credit balance is too low")
    assert not is_retryable("invalid API key")
    assert not is_retryable("permission denied")
    assert not is_retryable("claude -p returned empty output")


def test_retry_call_retries_transient_and_marks_final(monkeypatch):
    monkeypatch.setattr("agent_lab.cli_retry.time.sleep", lambda _delay: None)
    attempts = 0
    labels: list[tuple[int, int, str]] = []

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("429 rate limit")
        return "ok"

    assert (
        retry_call(
            flaky,
            max_attempts=3,
            base_delay_sec=0,
            jitter=False,
            on_retry_label=lambda a, m, r: labels.append((a, m, r)),
        )
        == "ok"
    )
    assert attempts == 3
    assert labels == [(2, 3, "429 rate limit"), (3, 3, "429 rate limit")]


def test_retry_call_does_not_retry_non_retryable(monkeypatch):
    monkeypatch.setattr("agent_lab.cli_retry.time.sleep", lambda _delay: None)
    attempts = 0

    def bad_auth() -> str:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("invalid API key")

    with pytest.raises(RuntimeError, match="invalid API key") as exc_info:
        retry_call(bad_auth, max_attempts=3, base_delay_sec=0, jitter=False)
    assert attempts == 1
    assert getattr(exc_info.value, "agent_lab_retry_attempts") == 1
    assert getattr(exc_info.value, "agent_lab_retryable") is False


def test_retry_call_honors_pre_marked_non_retryable_despite_retryable_wording(monkeypatch):
    """A message can contain a retryable-looking word (e.g. "timeout") while
    describing a decisive stall — the raiser's explicit mark must win over the
    text-pattern guess, or a real stall gets retried for no benefit."""
    monkeypatch.setattr("agent_lab.cli_retry.time.sleep", lambda _delay: None)
    attempts = 0

    def stalled() -> str:
        nonlocal attempts
        attempts += 1
        exc = RuntimeError("wall-clock timeout after 300s")
        exc.agent_lab_retryable = False  # type: ignore[attr-defined]
        raise exc

    with pytest.raises(RuntimeError, match="wall-clock timeout"):
        retry_call(stalled, max_attempts=3, base_delay_sec=0, jitter=False)
    assert attempts == 1
