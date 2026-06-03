"""Subprocess env allowlist (Centaur P0)."""

from __future__ import annotations

import os

from agent_lab.subprocess_env import isolated_process_env, subprocess_env


def test_subprocess_env_excludes_unlisted_secrets(monkeypatch):
    monkeypatch.setenv("PATH", "/bin")
    monkeypatch.setenv("HOME", "/tmp/home")
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "leak-me")
    env = subprocess_env()
    assert "SUPER_SECRET_TOKEN" not in env
    assert env["PATH"] == "/bin"


def test_subprocess_env_allows_agent_lab_prefix(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_FOO", "bar")
    assert subprocess_env()["AGENT_LAB_FOO"] == "bar"


def test_subprocess_env_excludes_anthropic_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("PATH", "/bin")
    assert "ANTHROPIC_API_KEY" not in subprocess_env()


def test_isolated_process_env_restores(monkeypatch):
    monkeypatch.setenv("PATH", "/original")
    monkeypatch.setenv("LEAK", "x")
    with isolated_process_env():
        assert os.environ.get("LEAK") is None
        os.environ["PATH"] = "/child"
    assert os.environ["PATH"] == "/original"
    assert os.environ["LEAK"] == "x"
