"""Kimi Work daimon lifecycle — attach to Kimi.app when running, else headless spawn."""

from __future__ import annotations

import atexit
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_lab.kimi.control_client import (
    ControlEndpoint,
    KimiWorkBridgeUnavailable,
    default_share_dir,
    daimon_config_path,
)

_CONTROL_READY_RE = re.compile(
    r"control server ready\s+url=(\S+)(?:\s+auth=\S+)?\s+token=(\S+)",
    re.IGNORECASE,
)
_SPAWN_TIMEOUT_S = 30.0
_STATE_POLL_INTERVAL_S = 0.25
_POST_SPAWN_PROBE_S = 8.0
_EXTERNAL_ATTACH_WAIT_S = 4.0

_owned_pid: int | None = None
_owned_proc: subprocess.Popen[str] | None = None
_owned_endpoint: ControlEndpoint | None = None
_supervisor_lock = threading.Lock()
_shutdown_registered = False


@dataclass(frozen=True)
class BundlePaths:
    node: Path
    runner_cli: Path
    adapter_root: Path
    runtime_binary: Path
    python_base: Path
    uv_path: Path


def agent_main_dir(share_dir: Path | None = None) -> Path:
    share = share_dir or default_share_dir()
    return share / "daimon" / "agents" / "main"


def runner_state_path(share_dir: Path | None = None) -> Path:
    return agent_main_dir(share_dir) / "runner.state.json"


def lock_owner_path(share_dir: Path | None = None) -> Path:
    return agent_main_dir(share_dir) / "runner.lock" / "owner.json"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_lock_owner_pid(share_dir: Path | None = None) -> int | None:
    path = lock_owner_path(share_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    pid = data.get("pid")
    try:
        return int(pid)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def read_runner_state(share_dir: Path | None = None) -> dict[str, Any]:
    path = runner_state_path(share_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def endpoint_from_runner_state(share_dir: Path | None = None) -> ControlEndpoint | None:
    """Runner.state control hint (not SSOT for agent-lab-owned spawn)."""
    state = read_runner_state(share_dir)
    control = state.get("control")
    if not isinstance(control, dict):
        return None
    endpoint = control.get("endpoint")
    if not isinstance(endpoint, dict):
        return None
    url = str(endpoint.get("url") or "").strip()
    auth = endpoint.get("auth")
    token = ""
    auth_mode = "loopback-dev-token"
    if isinstance(auth, dict):
        token = str(auth.get("token") or "").strip()
        auth_mode = str(auth.get("mode") or auth_mode).strip() or auth_mode
    if not url or not token:
        return None
    return ControlEndpoint(url=url, token=token, auth_mode=auth_mode)


def parse_control_ready_line(line: str) -> ControlEndpoint | None:
    match = _CONTROL_READY_RE.search(line)
    if not match:
        return None
    url, token = match.group(1), match.group(2)
    if not url or not token:
        return None
    return ControlEndpoint(url=url, token=token)


def resolve_bundle_paths() -> BundlePaths:
    if sys.platform != "darwin":
        raise KimiWorkBridgeUnavailable(
            "Kimi Work headless daimon spawn은 macOS + Kimi.app 번들이 필요합니다",
            code="kimi_work_bundle_unavailable",
        )
    base = Path("/Applications/Kimi.app/Contents/Resources/resources")
    node = base / "runtime" / "node"
    runner_cli = base / "daimon-bundle" / "app" / "daimon" / "dist" / "src" / "runner" / "cli.js"
    adapter_root = base / "daimon-bundle" / "app" / "daimon"
    runtime_binary = base / "daimon-bundle" / "bin" / "kimi-daimon"
    python_base = base / "daimon-bundle" / "runtime" / "python" / "cpython-3.12" / "bin" / "python3.12"
    uv_path = base / "daimon-bundle" / "runtime" / "uv" / "uv"
    missing = [p for p in (node, runner_cli, runtime_binary) if not p.is_file()]
    if not adapter_root.is_dir():
        missing.append(adapter_root)
    if missing:
        raise KimiWorkBridgeUnavailable(
            "Kimi.app daimon-bundle을 찾을 수 없습니다 — Kimi 앱 설치 후 재시도",
            code="kimi_work_bundle_unavailable",
        )
    return BundlePaths(
        node=node,
        runner_cli=runner_cli,
        adapter_root=adapter_root,
        runtime_binary=runtime_binary,
        python_base=python_base,
        uv_path=uv_path,
    )


def _openclaw_config_path(share_dir: Path) -> Path:
    path = share_dir / "daimon" / "runtime" / "openclaw-empty.json"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    return path


def _spawn_env(share_dir: Path, config_path: Path, bundle: BundlePaths) -> dict[str, str]:
    from agent_lab.subprocess_env import subprocess_env

    skills_root = share_dir / "skills"
    openclaw_config = _openclaw_config_path(share_dir)
    overrides: dict[str, str] = {
        "KIMI_SHARE_DIR": str(share_dir),
        "DAIMON_CONFIG_PATH": str(config_path),
        "OPENCLAW_CONFIG_PATH": str(openclaw_config),
        "DAIMON_BUNDLE_NODE_BIN": str(bundle.node),
        "DAIMON_ADAPTER_PACKAGE_ROOT": str(bundle.adapter_root),
        "DAIMON_RUNTIME_BINARY_PATH": str(bundle.runtime_binary),
        "DAIMON_OPENCLAW_COMPATIBILITY": "disabled",
        "DAIMON_PYTHON_RUNTIME_BACKGROUND_SYNC": "1",
        "KIMI_BASE_URL": "https://agent-gw.kimi.com/coding/",
        "KIMI_SKILLS_ROOT": str(skills_root),
    }
    if bundle.python_base.is_file():
        overrides["DAIMON_PYTHON_BASE_PATH"] = str(bundle.python_base)
    if bundle.uv_path.is_file():
        overrides["DAIMON_UV_PATH"] = str(bundle.uv_path)
    return subprocess_env(**overrides)


def _register_shutdown_once() -> None:
    global _shutdown_registered
    if _shutdown_registered:
        return
    atexit.register(shutdown_owned_daimon)
    _shutdown_registered = True


def _set_owned(proc: subprocess.Popen[str], endpoint: ControlEndpoint) -> None:
    global _owned_pid, _owned_proc, _owned_endpoint
    _owned_pid = proc.pid
    _owned_proc = proc
    _owned_endpoint = endpoint
    _register_shutdown_once()


def _clear_owned() -> None:
    global _owned_pid, _owned_proc, _owned_endpoint
    _owned_pid = None
    _owned_proc = None
    _owned_endpoint = None


def owned_endpoint() -> ControlEndpoint | None:
    """In-process SSOT for agent-lab-spawned daimon (stdout control server ready)."""
    if _owned_pid and _pid_alive(_owned_pid) and _owned_endpoint is not None:
        return _owned_endpoint
    return None


def _owned_endpoint_live() -> ControlEndpoint | None:
    """Return owned endpoint only when the process and Control WS are live."""
    cached = owned_endpoint()
    if cached is None:
        return None
    from agent_lab.kimi.control_client import probe_endpoint_ws, probe_recently_ok

    if probe_recently_ok():
        return cached
    if probe_endpoint_ws(cached):
        return cached
    shutdown_owned_daimon()
    return None


def _wait_for_control_probe(endpoint: ControlEndpoint, *, deadline: float) -> bool:
    from agent_lab.kimi.control_client import probe_endpoint_ws

    while time.monotonic() < deadline:
        if probe_endpoint_ws(endpoint):
            return True
        time.sleep(_STATE_POLL_INTERVAL_S)
    return False


def is_owned_pid(pid: int | None) -> bool:
    return pid is not None and _owned_pid is not None and pid == _owned_pid


def shutdown_owned_daimon() -> None:
    global _owned_pid, _owned_proc
    with _supervisor_lock:
        proc = _owned_proc
        pid = _owned_pid
        _clear_owned()
    from agent_lab.kimi.control_client import invalidate_endpoint_cache

    invalidate_endpoint_cache()
    if proc is not None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                if pid and _pid_alive(pid):
                    os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    elif pid and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def detach_owned_daimon() -> None:
    """Drop in-process ownership without terminating headless daimon (faster API restart)."""
    with _supervisor_lock:
        _clear_owned()
    from agent_lab.kimi.control_client import invalidate_endpoint_cache_only

    invalidate_endpoint_cache_only()


def _keep_daimon_on_api_shutdown() -> bool:
    import os

    return (os.getenv("AGENT_LAB_KIMI_WORK_KEEP_DAIMON_ON_SHUTDOWN") or "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def _wait_for_endpoint(
    *,
    stdout_lines: list[str],
    stderr_lines: list[str] | None = None,
    stdout_event: threading.Event,
    deadline: float,
) -> ControlEndpoint:
    """Block until spawn stdout/stderr emits control server ready (SSOT — not runner.state.json)."""
    stderr_lines = stderr_lines or []
    while time.monotonic() < deadline:
        for line in (*stdout_lines, *stderr_lines):
            parsed = parse_control_ready_line(line)
            if parsed is not None:
                return parsed
        if stdout_event.is_set():
            for line in (*stdout_lines, *stderr_lines):
                parsed = parse_control_ready_line(line)
                if parsed is not None:
                    return parsed
            break
        time.sleep(_STATE_POLL_INTERVAL_S)
    raise KimiWorkBridgeUnavailable(
        "headless daimon spawn 타임아웃 — stdout에서 control server ready 미수신",
        code="kimi_work_spawn_timeout",
    )


def _spawn_headless(share_dir: Path, config_path: Path) -> ControlEndpoint:
    bundle = resolve_bundle_paths()
    cmd = [str(bundle.node), str(bundle.runner_cli), "start", "--control"]
    env = _spawn_env(share_dir, config_path, bundle)
    deadline = time.monotonic() + _SPAWN_TIMEOUT_S
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    stdout_done = threading.Event()

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    def _read_stdout() -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                stdout_lines.append(line)
                if parse_control_ready_line(line) is not None:
                    break
        finally:
            stdout_done.set()

    def _read_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            line = line.rstrip("\n")
            stderr_lines.append(line)
            if len(stderr_lines) > 80:
                stderr_lines.pop(0)
            if parse_control_ready_line(line) is not None:
                stdout_done.set()
                break

    out_thread = threading.Thread(target=_read_stdout, daemon=True)
    err_thread = threading.Thread(target=_read_stderr, daemon=True)
    out_thread.start()
    err_thread.start()

    try:
        endpoint = _wait_for_endpoint(
            stdout_lines=stdout_lines,
            stderr_lines=stderr_lines,
            stdout_event=stdout_done,
            deadline=deadline,
        )
        _set_owned(proc, endpoint)
        if _wait_for_control_probe(endpoint, deadline=time.monotonic() + _POST_SPAWN_PROBE_S):
            return endpoint
        shutdown_owned_daimon()
        raise KimiWorkBridgeUnavailable(
            "headless daimon spawn 후 Control WS probe 실패",
            code="kimi_work_bridge_unavailable",
        )
    except KimiWorkBridgeUnavailable:
        shutdown_owned_daimon()
        hint = "\n".join(stderr_lines[-8:]).strip()
        raise KimiWorkBridgeUnavailable(
            f"headless daimon spawn 실패{(': ' + hint) if hint else ''}",
            code="kimi_work_spawn_failed",
        ) from None
    finally:
        out_thread.join(timeout=0.5)
        err_thread.join(timeout=0.5)


def _external_endpoint_from_runner_state(share_dir: Path) -> ControlEndpoint:
    endpoint = endpoint_from_runner_state(share_dir)
    if endpoint is None:
        raise KimiWorkBridgeUnavailable(
            "실행 중 daimon의 control endpoint를 찾을 수 없습니다 — runner.state.json 확인",
            code="kimi_work_endpoint_missing",
        )
    return endpoint


def _try_attach_external(share_dir: Path) -> ControlEndpoint | None:
    """Reuse a live external daimon (e.g. Kimi.app) when runner.state + WS probe succeed."""
    try:
        endpoint = _external_endpoint_from_runner_state(share_dir)
    except KimiWorkBridgeUnavailable:
        return None
    from agent_lab.kimi.control_client import probe_endpoint_ws

    if probe_endpoint_ws(endpoint):
        return endpoint
    return None


def _wait_for_external_attach(share_dir: Path) -> ControlEndpoint | None:
    """Poll runner.state until Kimi.app publishes a live control endpoint."""
    deadline = time.monotonic() + _EXTERNAL_ATTACH_WAIT_S
    while time.monotonic() < deadline:
        attached = _try_attach_external(share_dir)
        if attached is not None:
            return attached
        lock_pid = read_lock_owner_pid(share_dir)
        if not lock_pid or not _pid_alive(lock_pid):
            return None
        time.sleep(_STATE_POLL_INTERVAL_S)
    return None


def ensure_daimon(*, spawn_only: bool = False) -> ControlEndpoint:
    """Return a verified live control endpoint — attach external daimon or spawn headless."""
    share_dir = default_share_dir()
    config_path = daimon_config_path()
    if not config_path.is_file():
        raise KimiWorkBridgeUnavailable(
            "Kimi Work credentials 없음 — Kimi 앱에서 Work 최초 로그인 필요",
            code="kimi_work_not_configured",
        )

    if not spawn_only:
        attached = _try_attach_external(share_dir)
        if attached is not None:
            return attached

    cached = _owned_endpoint_live()
    if cached is not None:
        return cached

    lock_pid = read_lock_owner_pid(share_dir)
    if lock_pid and _pid_alive(lock_pid) and not spawn_only:
        if is_owned_pid(lock_pid):
            shutdown_owned_daimon()
        else:
            attached = _wait_for_external_attach(share_dir)
            if attached is not None:
                return attached
            state = read_runner_state(share_dir)
            lifecycle = str(state.get("lifecycleStatus") or "").strip().lower()
            if lifecycle == "stopped" and endpoint_from_runner_state(share_dir) is None:
                # Kimi.app lock/process may linger while daimon is down — spawn headless.
                pass
            else:
                raise KimiWorkBridgeUnavailable(
                    "Kimi 앱 daimon이 준비되지 않았습니다 — Kimi 앱을 완전히 종료한 뒤 bridge 재연결",
                    code="kimi_work_external_daimon",
                )

    with _supervisor_lock:
        cached = _owned_endpoint_live()
        if cached is not None:
            return cached
        return _spawn_headless(share_dir, config_path)
