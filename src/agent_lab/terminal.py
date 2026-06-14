"""PTY-backed terminal session manager (Phase 4)."""

from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import select
import signal
import struct
import termios
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from .subprocess_env import subprocess_env

_DEFAULT_SHELL = "/bin/zsh"

# One PTY session per (session_id, slot).  Slot "default" is used by the UI.
_sessions: dict[tuple[str, str], "PtySession"] = {}
_lock = Lock()


@dataclass
class PtySession:
    session_id: str
    slot: str
    pid: int
    fd: int
    cwd: str

    def alive(self) -> bool:
        try:
            os.kill(self.pid, 0)
            return True
        except ProcessLookupError:
            return False

    def close(self) -> None:
        try:
            os.kill(self.pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass


def _shell() -> str:
    return os.environ.get("SHELL", _DEFAULT_SHELL)


def spawn(session_id: str, cwd: Path, slot: str = "default") -> PtySession:
    """Fork a PTY shell, replacing any existing session for (session_id, slot)."""
    key = (session_id, slot)
    with _lock:
        old = _sessions.pop(key, None)
    if old:
        old.close()

    shell = _shell()
    env = subprocess_env()
    env.update(
        {
            "TERM": "xterm-256color",
            "HOME": os.path.expanduser("~"),
            "SHELL": shell,
        }
    )

    # Ensure cwd exists; fall back to home if not.
    cwd_str = str(cwd) if cwd.is_dir() else os.path.expanduser("~")

    pid, fd = pty.fork()
    if pid == 0:  # child process
        try:
            os.chdir(cwd_str)
        except OSError:
            pass
        os.execve(shell, [shell, "-i"], env)
        # unreachable

    sess = PtySession(session_id=session_id, slot=slot, pid=pid, fd=fd, cwd=cwd_str)
    with _lock:
        _sessions[key] = sess
    return sess


def get_session(session_id: str, slot: str = "default") -> PtySession | None:
    with _lock:
        return _sessions.get((session_id, slot))


def close_session(session_id: str, slot: str = "default") -> None:
    key = (session_id, slot)
    with _lock:
        sess = _sessions.pop(key, None)
    if sess:
        sess.close()


async def read_output(fd: int, max_bytes: int = 4096) -> bytes | None:
    """Read available bytes from PTY fd. Returns None on EOF/error."""
    loop = asyncio.get_event_loop()

    def _read() -> bytes | None:
        try:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                return os.read(fd, max_bytes)
            return b""
        except OSError:
            return None

    return await loop.run_in_executor(None, _read)


def write_input(fd: int, data: bytes) -> None:
    os.write(fd, data)


def resize(fd: int, rows: int, cols: int) -> None:
    s = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, s)
