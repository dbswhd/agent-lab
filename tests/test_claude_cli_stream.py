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
    from agent_lab import claude_cli

    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake_bin))
    monkeypatch.setattr(claude_cli, "resolve_claude_roots", lambda _perms: [])
    monkeypatch.setattr(
        "agent_lab.workspace_roots.discuss_primary_workspace",
        lambda _perms: tmp_path,
    )
    monkeypatch.setattr(
        "agent_lab.run_control.register_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr(
        "agent_lab.run_control.unregister_child_process",
        lambda _proc: None,
    )
    monkeypatch.setattr("agent_lab.run_control.is_cancelled", lambda: False)
    monkeypatch.setattr(
        "agent_lab.agent_hooks_materializer.native_claude_hooks_overlay",
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
