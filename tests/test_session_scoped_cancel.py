"""Session-scoped cancel must not affect other sessions."""

from __future__ import annotations

import subprocess
import sys
import time

from agent_lab.run_control import (
    clear_cancel,
    is_cancelled,
    register_child_process,
    request_cancel,
    set_run_session_id,
    unregister_child_process,
)


def test_session_cancel_does_not_affect_other_session() -> None:
    clear_cancel()
    token_a = set_run_session_id("session-a")
    proc_a = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    register_child_process(proc_a, session_id="session-a")
    token_b = set_run_session_id("session-b")
    proc_b = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    register_child_process(proc_b, session_id="session-b")
    try:
        time.sleep(0.15)
        request_cancel("session-a")
        assert is_cancelled("session-a")
        assert not is_cancelled("session-b")
        proc_a.wait(timeout=5)
        assert proc_a.returncode is not None
        assert proc_b.poll() is None
    finally:
        proc_b.kill()
        proc_b.wait(timeout=5)
        unregister_child_process(proc_a)
        unregister_child_process(proc_b)
        clear_cancel()
        from agent_lab.run_control import reset_run_session_id

        reset_run_session_id(token_b)
        reset_run_session_id(token_a)
