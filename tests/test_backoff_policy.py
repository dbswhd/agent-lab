"""Tests for agent_lab.backoff_policy."""

from __future__ import annotations

import importlib
from unittest import mock

import pytest

from agent_lab import backoff_policy
from agent_lab.backoff_policy import next_backoff, wait


@pytest.mark.parametrize(
    "attempt,base,expected",
    [
        (1, 1.5, 1.5),
        (2, 1.5, 3.0),
        (3, 0.0, 0.0),
    ],
)
def test_next_backoff(attempt: int, base: float, expected: float) -> None:
    assert next_backoff(attempt=attempt, base_sec=base) == expected


def test_next_backoff_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_BACKOFF_BASE_SEC", "3.5")
    importlib.reload(backoff_policy)
    assert backoff_policy.next_backoff(attempt=2) == pytest.approx(7.0)
    monkeypatch.delenv("AGENT_LAB_BACKOFF_BASE_SEC", raising=False)
    importlib.reload(backoff_policy)


def test_sleep_base_sec_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_BACKOFF_BASE_SEC", "1.25")
    importlib.reload(backoff_policy)
    assert backoff_policy.sleep_base_sec == pytest.approx(1.25)
    monkeypatch.delenv("AGENT_LAB_BACKOFF_BASE_SEC", raising=False)
    importlib.reload(backoff_policy)


def test_sleep_base_sec_env_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LAB_BACKOFF_BASE_SEC", "not-a-float")
    importlib.reload(backoff_policy)
    assert backoff_policy.sleep_base_sec == pytest.approx(2.0)
    monkeypatch.delenv("AGENT_LAB_BACKOFF_BASE_SEC", raising=False)
    importlib.reload(backoff_policy)


def test_wait_sleeps_once(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    with mock.patch("agent_lab.backoff_policy.time.sleep", side_effect=lambda value: sleeps.append(value)):
        wait(attempt=2, base_sec=1.0)
    assert sleeps == [2.0]
