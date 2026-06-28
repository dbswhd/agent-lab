"""Claude CLI stream-json bridge path."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace


class _StreamProc:
    def __init__(self, lines: list[str], *, returncode: int = 0) -> None:
        self._lines = list(lines)
        self._idx = 0
        self.returncode: int | None = None
        self._final_rc = returncode
        self.stdout = self
        self.stderr = SimpleNamespace(read=lambda: "")

    def poll(self) -> int | None:
        return self.returncode

    def readline(self) -> str:
        if self._idx < len(self._lines):
            line = self._lines[self._idx] + "\n"
            self._idx += 1
            return line
        self.returncode = self._final_rc
        return ""

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = self._final_rc
        return self._final_rc

    def kill(self) -> None:
        self.returncode = self._final_rc


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_claude_invoke_stream_json_emits_bridge_events(monkeypatch, tmp_path):
    from agent_lab.claude import cli as claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace.roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
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
    monkeypatch.setattr(
        "agent_lab.agent.hooks_materializer.native_claude_hooks_overlay",
        lambda *_a, **_k: _NullCtx(),
    )

    lines = [
        json.dumps(
            {
                "type": "stream_event",
                "event": {"delta": {"type": "text_delta", "text": "Hello"}},
            }
        ),
        json.dumps({"type": "result", "result": "Hello world"}),
    ]

    def fake_popen(cmd, **_kwargs):
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--verbose" in cmd
        assert "--include-partial-messages" in cmd
        return _StreamProc(lines)

    def fake_select(rlist, wlist, xlist, timeout):
        if rlist and getattr(rlist[0], "_lines", None) is not None:
            proc = rlist[0]
            if proc._idx < len(proc._lines):
                return (rlist, [], [])
            proc.returncode = proc._final_rc
            return ([], [], [])
        return ([], [], [])

    monkeypatch.setattr("select.select", fake_select)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    bridge: list[tuple[str, dict]] = []

    out = claude_cli.invoke(
        "sys",
        "user",
        on_bridge_event=lambda k, d: bridge.append((k, d)),
    )
    assert out == "Hello world"
    assert ("text", {"text": "Hello"}) in bridge


def test_claude_stream_skips_assistant_text_after_text_delta(monkeypatch, tmp_path):
    from agent_lab.claude import cli as claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace.roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
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
    monkeypatch.setattr(
        "agent_lab.agent.hooks_materializer.native_claude_hooks_overlay",
        lambda *_a, **_k: _NullCtx(),
    )

    lines = [
        json.dumps(
            {
                "type": "stream_event",
                "event": {"delta": {"type": "text_delta", "text": "Hello world"}},
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Hello world"}]},
            }
        ),
        json.dumps({"type": "result", "result": "Hello world"}),
    ]

    def fake_popen(cmd, **_kwargs):
        return _StreamProc(lines)

    def fake_select(rlist, wlist, xlist, timeout):
        if rlist and getattr(rlist[0], "_lines", None) is not None:
            proc = rlist[0]
            if proc._idx < len(proc._lines):
                return (rlist, [], [])
            proc.returncode = proc._final_rc
            return ([], [], [])
        return ([], [], [])

    monkeypatch.setattr("select.select", fake_select)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    bridge: list[tuple[str, dict]] = []

    claude_cli.invoke(
        "sys",
        "user",
        on_bridge_event=lambda k, d: bridge.append((k, d)),
    )
    text_events = [d["text"] for k, d in bridge if k == "text"]
    assert text_events == ["Hello world"]
    assert "".join(text_events) == "Hello world"


def test_claude_stream_raises_cancelled_when_killed_after_cancel(monkeypatch, tmp_path):
    from agent_lab.claude import cli as claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace.roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
    monkeypatch.setattr(
        "agent_lab.run.control.register_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr(
        "agent_lab.run.control.unregister_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr(
        "agent_lab.claude.cli.ensure_claude_headless_ready",
        lambda **_kw: None,
    )
    monkeypatch.setattr(
        "agent_lab.agent.hooks_materializer.native_claude_hooks_overlay",
        lambda *_a, **_k: _NullCtx(),
    )

    class _KilledProc(_StreamProc):
        def readline(self) -> str:
            self.returncode = -9
            return ""

    def fake_popen(cmd, **_kwargs):
        return _KilledProc([])

    def fake_select(rlist, wlist, xlist, timeout):
        from agent_lab.run.control import request_cancel

        request_cancel()
        return (rlist, [], [])

    monkeypatch.setattr("select.select", fake_select)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    import pytest
    from agent_lab.run.control import RoomRunCancelled, clear_cancel

    clear_cancel()
    with pytest.raises(RoomRunCancelled):
        claude_cli.invoke("sys", "user", on_bridge_event=lambda _k, _d: None)
    clear_cancel()


class _EofSpinProc:
    """CLI exits without a result line; select keeps reporting stdout readable."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.stdout = self
        self.stderr = SimpleNamespace(read=lambda: "")

    def poll(self) -> int | None:
        return self.returncode

    def readline(self) -> str:
        if self.returncode is None:
            self.returncode = 0
        return ""

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self) -> None:
        if self.returncode is None:
            self.returncode = -9


def test_claude_stream_fails_fast_on_stderr_usage_limit(monkeypatch, tmp_path):
    from agent_lab.claude import cli as claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setenv("CLAUDE_ROOM_IDLE_TIMEOUT_SEC", "1")
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace.roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
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
    monkeypatch.setattr(
        "agent_lab.agent.hooks_materializer.native_claude_hooks_overlay",
        lambda *_a, **_k: _NullCtx(),
    )

    class _LimitProc(_StreamProc):
        def __init__(self) -> None:
            super().__init__([], returncode=1)
            self.stderr = SimpleNamespace(read=lambda: "ERROR: usage limit reached\n")

    def fake_popen(cmd, **_kwargs):
        return _LimitProc()

    def fake_select(rlist, wlist, xlist, timeout):
        if rlist and getattr(rlist[0], "stderr", None) is not None:
            return (rlist, [], [])
        return ([], [], [])

    monkeypatch.setattr("select.select", fake_select)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    import pytest

    with pytest.raises(RuntimeError, match="usage limit"):
        claude_cli.invoke("sys", "user", on_bridge_event=lambda _k, _d: None)


def test_claude_stream_exits_when_child_eof_without_result(monkeypatch, tmp_path):
    """Avoid busy-loop when claude exits but stdout stays select-readable."""
    from agent_lab.claude import cli as claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace.roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
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
    monkeypatch.setattr(
        "agent_lab.agent.hooks_materializer.native_claude_hooks_overlay",
        lambda *_a, **_k: _NullCtx(),
    )

    proc = _EofSpinProc()

    def fake_popen(cmd, **_kwargs):
        return proc

    def fake_select(rlist, _wlist, _xlist, _timeout):
        return (rlist, [], [])

    monkeypatch.setattr("select.select", fake_select)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    import pytest

    with pytest.raises(RuntimeError, match="empty result"):
        claude_cli.invoke("sys", "user", on_bridge_event=lambda _k, _d: None)
