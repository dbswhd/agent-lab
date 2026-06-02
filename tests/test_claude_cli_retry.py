from __future__ import annotations

import subprocess


def test_claude_cli_retries_transient_subprocess_failure(monkeypatch, tmp_path):
    from agent_lab import claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setenv("AGENT_LAB_CLI_RETRY_MAX", "2")
    monkeypatch.setenv("AGENT_LAB_CLI_RETRY_BASE_SEC", "0")
    monkeypatch.setattr("agent_lab.cli_retry.time.sleep", lambda _delay: None)
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace_roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
    calls = 0

    def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(
                _args[0],
                52,
                stdout="",
                stderr="ERROR: temporarily unavailable",
            )
        return subprocess.CompletedProcess(_args[0], 0, stdout="done\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    activity: list[str] = []

    assert claude_cli.invoke("", "hello", on_activity=activity.append) == "done"
    assert calls == 2
    assert activity == ["재시도 2/2 — Claude CLI 일시 오류"]


def test_claude_cli_does_not_retry_empty_output(monkeypatch, tmp_path):
    from agent_lab import claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setenv("AGENT_LAB_CLI_RETRY_MAX", "3")
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace_roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
    calls = 0

    def fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(_args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    try:
        claude_cli.invoke("", "hello")
    except RuntimeError as exc:
        assert "empty output" in str(exc)
    else:
        raise AssertionError("expected empty-output failure")
    assert calls == 1
