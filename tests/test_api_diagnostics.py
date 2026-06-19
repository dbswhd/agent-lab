"""API diagnostics endpoint."""

from __future__ import annotations

from agent_lab.api_diagnostics import (
    build_diagnostics_payload,
    mask_tool_path,
    read_boot_log_tail,
)


def test_mask_tool_path_hides_home_prefix():
    home = __import__("pathlib").Path.home()
    raw = str(home / "bin/codex")
    assert mask_tool_path(raw) == "~/bin/codex"


def test_build_diagnostics_payload_shape():
    payload = build_diagnostics_payload()
    assert payload["ok"] is True
    assert isinstance(payload["pid"], int)
    assert payload["uptime_seconds"] >= 0
    assert "sessions_dir" in payload
    assert "port_status" in payload
    assert "agent_tools" in payload
    assert "boot_log_path" in payload
    assert "bridge_audit" in payload
    assert "verification" in payload
    assert payload["verification"]["lanes"]["fast"]["status"] in {
        "passed",
        "failed",
        "not_run",
        "running",
        "unknown",
    }
    assert isinstance(read_boot_log_tail(), list)
