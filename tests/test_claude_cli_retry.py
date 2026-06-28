from __future__ import annotations

import subprocess
import time


class _FakeProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    def poll(self) -> int:
        return self.returncode

    def communicate(self) -> tuple[str, str]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode


def _patch_claude_popen(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _delay: None)
    monkeypatch.setattr(
        "agent_lab.run.control.register_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr(
        "agent_lab.run.control.unregister_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr("agent_lab.run.control.is_cancelled", lambda: False)
    monkeypatch.setattr(
        "agent_lab.claude.cli.ensure_claude_headless_ready",
        lambda **_kw: None,
    )


def test_claude_cli_retries_transient_subprocess_failure(monkeypatch, tmp_path):
    from agent_lab.claude import cli as claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setenv("AGENT_LAB_CLI_RETRY_MAX", "2")
    monkeypatch.setenv("AGENT_LAB_CLI_RETRY_BASE_SEC", "0")
    monkeypatch.setattr("agent_lab.cli_retry.time.sleep", lambda _delay: None)
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace.roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
    calls = 0

    def fake_popen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _FakeProc(52, "", "ERROR: temporarily unavailable")
        return _FakeProc(0, "done\n", "")

    _patch_claude_popen(monkeypatch)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    activity: list[str] = []

    assert claude_cli.invoke("", "hello", on_activity=activity.append) == "done"
    assert calls == 2
    assert activity == ["재시도 2/2 — Claude CLI 일시 오류"]


def test_claude_cli_does_not_retry_empty_output(monkeypatch, tmp_path):
    from agent_lab.claude import cli as claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setenv("AGENT_LAB_CLI_RETRY_MAX", "3")
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace.roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
    calls = 0

    def fake_popen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _FakeProc(0, "", "")

    _patch_claude_popen(monkeypatch)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    try:
        claude_cli.invoke("", "hello")
    except RuntimeError as exc:
        assert "empty output" in str(exc)
    else:
        raise AssertionError("expected empty-output failure")
    assert calls == 1
