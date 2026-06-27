from __future__ import annotations

import subprocess
import sys
import time

from agent_lab.run_control import (
    clear_cancel,
    is_cancelled,
    register_child_process,
    register_cursor_run,
    request_cancel,
    terminate_active_children,
    unregister_child_process,
)


def test_request_cancel_terminates_registered_child() -> None:
    clear_cancel()
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    register_child_process(proc)
    try:
        time.sleep(0.15)
        killed = request_cancel()
        assert killed >= 1
        assert is_cancelled()
        proc.wait(timeout=5)
        assert proc.returncode is not None
    finally:
        unregister_child_process(proc)
        clear_cancel()


def test_terminate_active_children_noop_when_empty() -> None:
    clear_cancel()
    assert terminate_active_children() == 0


def test_force_reset_run_lock_preserves_cancel_flag() -> None:
    from agent_lab.run_control import end_run, force_reset_run_lock, try_begin_run

    clear_cancel()
    assert try_begin_run() is True
    request_cancel()
    assert is_cancelled()
    force_reset_run_lock()
    assert is_cancelled()
    end_run()
    clear_cancel()


def test_run_lock_status_includes_session_context() -> None:
    from agent_lab.run_control import end_run, run_lock_status, try_begin_run

    assert try_begin_run(session_id="sess-a", run_kind="execute", label="Execute #1") is True
    try:
        status = run_lock_status()
        assert status["locked"] is True
        assert status["session_id"] == "sess-a"
        assert status["run_kind"] == "execute"
        assert status["label"] == "Execute #1"
    finally:
        end_run()


def test_request_cancel_cancels_cursor_run() -> None:
    clear_cancel()

    class FakeRun:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

        def wait(self) -> None:
            for _ in range(40):
                if self.cancelled:
                    return
                time.sleep(0.05)
            raise TimeoutError("wait timed out")

    run = FakeRun()
    register_cursor_run(run)
    killed = request_cancel()
    assert killed >= 1
    assert run.cancelled
    clear_cancel()
