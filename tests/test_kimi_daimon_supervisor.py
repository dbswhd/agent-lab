"""Kimi Work daimon supervisor — attach or headless spawn."""

from __future__ import annotations

import json
from pathlib import Path
import threading
import time

import pytest

from agent_lab.kimi.control_client import ControlEndpoint, KimiWorkBridgeUnavailable
from agent_lab.kimi.daimon_supervisor import (
    endpoint_from_runner_state,
    ensure_daimon,
    is_owned_pid,
    parse_control_ready_line,
    read_lock_owner_pid,
    resolve_bundle_paths,
    shutdown_owned_daimon,
)


def test_parse_control_ready_line() -> None:
    line = "control server ready url=ws://127.0.0.1:59260/control token=abc123"
    ep = parse_control_ready_line(line)
    assert ep == ControlEndpoint(url="ws://127.0.0.1:59260/control", token="abc123")
    with_auth = (
        "2026-06-19T15:05:15.342Z INFO standalone-runtime control server ready "
        "url=ws://127.0.0.1:59947/control auth=loopback-dev-token token=tok123"
    )
    ep2 = parse_control_ready_line(with_auth)
    assert ep2 == ControlEndpoint(url="ws://127.0.0.1:59947/control", token="tok123")
    assert parse_control_ready_line("noise") is None


def test_endpoint_from_runner_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path))
    main = tmp_path / "daimon" / "agents" / "main"
    main.mkdir(parents=True)
    state = {
        "control": {
            "endpoint": {
                "url": "ws://127.0.0.1:9/control",
                "auth": {"mode": "loopback-dev-token", "token": "tok"},
            }
        }
    }
    (main / "runner.state.json").write_text(json.dumps(state), encoding="utf-8")
    ep = endpoint_from_runner_state()
    assert ep is not None
    assert ep.url.endswith("/control")
    assert ep.token == "tok"


def test_attaches_external_daimon_when_ws_probe_ok(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path))
    share = tmp_path
    config = share / "daimon" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")
    main = share / "daimon" / "agents" / "main"
    main.mkdir(parents=True)
    (main / "runner.state.json").write_text(
        json.dumps(
            {
                "control": {
                    "endpoint": {
                        "url": "ws://127.0.0.1:65027/control",
                        "auth": {"mode": "loopback-dev-token", "token": "tok"},
                    }
                }
            },
        ),
        encoding="utf-8",
    )
    (main / "runner.lock" / "owner.json").parent.mkdir(parents=True)
    (main / "runner.lock" / "owner.json").write_text(json.dumps({"pid": 999999}), encoding="utf-8")

    fake = ControlEndpoint(url="ws://127.0.0.1:65027/control", token="tok")

    def _fake_alive(pid: int) -> bool:
        return pid == 999999

    monkeypatch.setattr("agent_lab.kimi.daimon_supervisor._pid_alive", _fake_alive)
    monkeypatch.setattr("agent_lab.kimi.control_client.probe_endpoint_ws", lambda _ep: True)
    ep = ensure_daimon()
    assert ep == fake


def test_external_daimon_ws_probe_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path))
    share = tmp_path
    config = share / "daimon" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}", encoding="utf-8")
    main = share / "daimon" / "agents" / "main"
    lock_dir = main / "runner.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner.json").write_text(json.dumps({"pid": 999999}), encoding="utf-8")
    (main / "runner.state.json").write_text(
        json.dumps({"lifecycleStatus": "running", "control": {"endpoint": None}}),
        encoding="utf-8",
    )

    def _fake_alive(pid: int) -> bool:
        return pid == 999999

    monkeypatch.setattr("agent_lab.kimi.daimon_supervisor._pid_alive", _fake_alive)
    monkeypatch.setattr("agent_lab.kimi.control_client.probe_endpoint_ws", lambda _ep: False)
    monkeypatch.setattr(
        "agent_lab.kimi.daimon_supervisor._wait_for_external_attach",
        lambda _share: None,
    )
    with pytest.raises(KimiWorkBridgeUnavailable) as exc:
        ensure_daimon()
    assert exc.value.code == "kimi_work_external_daimon"


def test_is_owned_pid_tracks_spawned(monkeypatch: pytest.MonkeyPatch) -> None:
    shutdown_owned_daimon()
    assert is_owned_pid(12345) is False
    import agent_lab.kimi.daimon_supervisor as sup

    monkeypatch.setattr(sup, "_pid_alive", lambda pid: pid == 4242)
    sup._owned_pid = 4242  # noqa: SLF001
    sup._owned_endpoint = ControlEndpoint(url="ws://127.0.0.1:1/control", token="t")  # noqa: SLF001
    assert is_owned_pid(4242) is True
    assert sup.owned_endpoint() is not None
    shutdown_owned_daimon()
    assert is_owned_pid(4242) is False
    assert sup.owned_endpoint() is None


def test_wait_for_endpoint_stdout_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_lab.kimi.daimon_supervisor import _wait_for_endpoint

    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path))
    main = tmp_path / "daimon" / "agents" / "main"
    main.mkdir(parents=True)
    state = {
        "control": {
            "endpoint": {
                "url": "ws://127.0.0.1:1/control",
                "auth": {"token": "stale"},
            }
        }
    }
    (main / "runner.state.json").write_text(json.dumps(state), encoding="utf-8")
    done = threading.Event()
    done.set()
    with pytest.raises(KimiWorkBridgeUnavailable):
        _wait_for_endpoint(
            stdout_lines=[],
            stderr_lines=[],
            stdout_event=done,
            deadline=time.monotonic() + 0.5,
        )


def test_read_lock_owner_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIMI_SHARE_DIR", str(tmp_path))
    lock = tmp_path / "daimon" / "agents" / "main" / "runner.lock"
    lock.mkdir(parents=True)
    (lock / "owner.json").write_text(json.dumps({"pid": 77}), encoding="utf-8")
    assert read_lock_owner_pid() == 77


@pytest.mark.skipif(
    not Path("/Applications/Kimi.app/Contents/Resources/resources/runtime/node").is_file(),
    reason="Kimi.app not installed",
)
def test_resolve_bundle_paths_when_kimi_app_installed() -> None:
    bundle = resolve_bundle_paths()
    assert bundle.node.name == "node"
    assert bundle.adapter_root.is_dir()
    assert bundle.runner_cli.is_file()
