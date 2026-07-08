"""env_flags.py — canonical env-var truthy parsing (2026-07-09 dedup SSOT)."""

from __future__ import annotations

import pytest

from agent_lab.env_flags import FALSY, TRUTHY, env_bool, is_falsy, is_truthy, optional_env_int


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "Yes", "on", " on "])
def test_is_truthy_accepts_known_spellings(raw: str) -> None:
    assert is_truthy(raw) is True


@pytest.mark.parametrize("raw", [None, "", "0", "false", "no", "off", "banana"])
def test_is_truthy_rejects_everything_else(raw) -> None:
    assert is_truthy(raw) is False


@pytest.mark.parametrize("raw", ["0", "false", "FALSE", "no", "off"])
def test_is_falsy_accepts_known_spellings(raw: str) -> None:
    assert is_falsy(raw) is True


@pytest.mark.parametrize("raw", [None, "", "1", "true", "banana"])
def test_is_falsy_rejects_everything_else(raw) -> None:
    assert is_falsy(raw) is False


def test_env_bool_unset_returns_default(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_TEST_FLAG_XYZ", raising=False)
    assert env_bool("AGENT_LAB_TEST_FLAG_XYZ") is False
    assert env_bool("AGENT_LAB_TEST_FLAG_XYZ", default=True) is True


def test_env_bool_empty_string_treated_as_unset(monkeypatch) -> None:
    """FOO="" must fall back to default, same as FOO unset (matches every
    pre-existing call site's `raw is None or raw.strip() == ""` guard)."""
    monkeypatch.setenv("AGENT_LAB_TEST_FLAG_XYZ", "")
    assert env_bool("AGENT_LAB_TEST_FLAG_XYZ", default=True) is True
    assert env_bool("AGENT_LAB_TEST_FLAG_XYZ", default=False) is False


def test_env_bool_set_true(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TEST_FLAG_XYZ", "1")
    assert env_bool("AGENT_LAB_TEST_FLAG_XYZ") is True
    assert env_bool("AGENT_LAB_TEST_FLAG_XYZ", default=False) is True


def test_env_bool_set_false_overrides_default_true(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TEST_FLAG_XYZ", "0")
    assert env_bool("AGENT_LAB_TEST_FLAG_XYZ", default=True) is False


def test_truthy_falsy_sets_are_the_project_spellings() -> None:
    assert TRUTHY == {"1", "true", "yes", "on"}
    assert FALSY == {"0", "false", "no", "off"}


def test_optional_env_int_returns_none_when_all_unset(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_TEST_INT_A", raising=False)
    monkeypatch.delenv("AGENT_LAB_TEST_INT_B", raising=False)
    assert optional_env_int("AGENT_LAB_TEST_INT_A", "AGENT_LAB_TEST_INT_B") is None


def test_optional_env_int_first_set_key_wins(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_TEST_INT_A", raising=False)
    monkeypatch.setenv("AGENT_LAB_TEST_INT_B", "45")
    assert optional_env_int("AGENT_LAB_TEST_INT_A", "AGENT_LAB_TEST_INT_B") == 45


def test_optional_env_int_earlier_key_takes_priority(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_LAB_TEST_INT_A", "10")
    monkeypatch.setenv("AGENT_LAB_TEST_INT_B", "20")
    assert optional_env_int("AGENT_LAB_TEST_INT_A", "AGENT_LAB_TEST_INT_B") == 10
