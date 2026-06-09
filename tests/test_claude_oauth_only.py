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
        "agent_lab.run_control.register_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr(
        "agent_lab.run_control.unregister_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr("agent_lab.run_control.is_cancelled", lambda: False)


def test_claude_invoke_never_injects_api_key(monkeypatch, tmp_path) -> None:
    from agent_lab import claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-reach-child")
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace_roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )

    captured_env: dict[str, str] | None = None

    def fake_popen(*_args, **kwargs):
        nonlocal captured_env
        captured_env = dict(kwargs.get("env") or {})
        return _FakeProc(0, "ok\n", "")

    _patch_claude_popen(monkeypatch)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "agent_lab.credential_store.get_credential_chain",
        lambda _provider: [("primary", "sk-from-store")],
    )

    assert claude_cli.invoke("", "hello") == "ok"
    assert captured_env is not None
    assert "ANTHROPIC_API_KEY" not in captured_env
    assert "ANTHROPIC_AUTH_TOKEN" not in captured_env
