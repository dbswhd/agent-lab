from __future__ import annotations

import subprocess


def _disable_codex_proxy(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_LAB_CODEX_PROXY", raising=False)
    monkeypatch.setattr(
        "agent_lab.runtime.adapters.codex.can_route_codex_proxy",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "agent_lab.codex_oauth.call_with_codex_oauth_fallback",
        lambda fn, **kwargs: fn(None),
    )


def test_codex_cli_retries_transient_subprocess_failure(monkeypatch, tmp_path):
    from agent_lab import codex_cli

    _disable_codex_proxy(monkeypatch)
    fake_bin = tmp_path / "codex"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CODEX_BIN", str(fake_bin))
    monkeypatch.setenv("AGENT_LAB_CLI_RETRY_MAX", "2")
    monkeypatch.setenv("AGENT_LAB_CLI_RETRY_BASE_SEC", "0")
    monkeypatch.setattr("agent_lab.cli_retry.time.sleep", lambda _delay: None)
    monkeypatch.setattr(
        "agent_lab.workspace.roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
    calls = 0

    def fake_run(cmd, *args, **kwargs):
        nonlocal calls
        calls += 1
        out_path = cmd[cmd.index("-o") + 1]
        if calls == 1:
            return subprocess.CompletedProcess(
                cmd,
                52,
                stdout="",
                stderr="ERROR: temporarily unavailable",
            )
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("codex done\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert codex_cli.invoke("", "hello", room_turn=False) == "codex done"
    assert calls == 2


def test_codex_cli_room_only_retry_env_skips_non_room_retry(monkeypatch, tmp_path):
    from agent_lab import codex_cli

    _disable_codex_proxy(monkeypatch)
    fake_bin = tmp_path / "codex"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CODEX_BIN", str(fake_bin))
    monkeypatch.setenv("AGENT_LAB_CLI_RETRY_MAX", "3")
    monkeypatch.setenv("AGENT_LAB_CLI_RETRY_ROOM_ONLY", "1")
    monkeypatch.setattr(
        "agent_lab.workspace.roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
    calls = 0

    def fake_run(cmd, *args, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            cmd,
            52,
            stdout="",
            stderr="ERROR: temporarily unavailable",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    try:
        codex_cli.invoke("", "hello", room_turn=False)
    except RuntimeError as exc:
        assert "exit 52" in str(exc)
    else:
        raise AssertionError("expected codex failure")
    assert calls == 1
