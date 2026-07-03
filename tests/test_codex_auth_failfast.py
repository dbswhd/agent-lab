"""Codex OAuth fail-fast: revoked refresh token must abort turns immediately.

Regression for 2026-07-02: a server-side token revocation left `codex exec`
spinning in a 401 refresh loop until the idle timeout, while preflight
(`codex login status` + profile_exists) kept reporting ready — and
`/login codex` answered "이미 로그인되어 있습니다" without starting an auth run.
"""

from __future__ import annotations

import sys

import pytest

from agent_lab.codex.cli import _run_codex, is_codex_auth_revoked_output
from agent_lab.codex.oauth import (
    auth_revoked_marker_path,
    clear_codex_auth_revoked,
    codex_auth_revoked_detail,
    codex_oauth_ready,
    mark_codex_auth_revoked,
)

REVOKED_LINE = (
    "2026-07-02T11:08:38Z ERROR codex_login::auth::manager: Failed to refresh token: "
    "Your access token could not be refreshed because your refresh token was revoked. "
    "Please log out and sign in again."
)


@pytest.fixture(autouse=True)
def _config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(tmp_path / "config"))
    yield


def test_detects_revoked_refresh_token_lines():
    assert is_codex_auth_revoked_output(REVOKED_LINE)
    assert is_codex_auth_revoked_output('{"code": "refresh_token_invalidated"}')
    assert is_codex_auth_revoked_output("ERROR: authentication token has been invalidated")


def test_unrelated_401s_do_not_trigger_failfast():
    # The same stderr stream carries 401s from unrelated MCP servers — those
    # must not kill the turn.
    assert not is_codex_auth_revoked_output(
        "rmcp::transport::worker: worker quit with fatal: AuthRequired "
        '(www_authenticate_header: Bearer realm="OAuth", '
        'resource_metadata="https://mcp.linear.app/...", error="invalid_token")'
    )
    assert not is_codex_auth_revoked_output("HTTP error: 401 Unauthorized")
    assert not is_codex_auth_revoked_output("codex exec running fine")


def test_marker_roundtrip_and_manual_clear():
    assert codex_auth_revoked_detail() is None
    mark_codex_auth_revoked("codex exec died on revoked OAuth refresh token")
    detail = codex_auth_revoked_detail()
    assert detail is not None
    assert "revoked" in detail
    clear_codex_auth_revoked()
    assert codex_auth_revoked_detail() is None


def test_marker_autoclears_after_relogin(tmp_path, monkeypatch):
    import agent_lab.codex.oauth as oauth

    fake_auth = tmp_path / "auth.json"
    monkeypatch.setattr(oauth, "live_auth_path", lambda: fake_auth)

    mark_codex_auth_revoked("revoked")
    assert codex_auth_revoked_detail() is not None

    # Re-login rewrites auth.json with a newer mtime than the marker.
    import os
    import time

    fake_auth.write_text("{}", encoding="utf-8")
    marker_mtime = auth_revoked_marker_path().stat().st_mtime
    os.utime(fake_auth, (marker_mtime + 5, marker_mtime + 5))

    assert codex_auth_revoked_detail() is None
    # And the marker file itself was removed (one-shot auto-clear).
    assert not auth_revoked_marker_path().is_file()
    time.sleep(0)  # keep imports used


def test_codex_oauth_ready_false_while_revoked(monkeypatch):
    import agent_lab.codex.oauth as oauth

    # Even with a stored profile present (it holds the same revoked token),
    # readiness must be False while the marker is active.
    monkeypatch.setattr(oauth, "profile_exists", lambda slot: True)
    mark_codex_auth_revoked("revoked")
    ok, detail = codex_oauth_ready()
    assert ok is False
    assert detail is not None
    assert "/login" in detail


def test_provider_login_status_logged_out_while_revoked(monkeypatch):
    import subprocess

    from agent_lab.auth_runs import _interpret_cli_status, get_provider

    spec = get_provider("codex")
    assert spec is not None
    mark_codex_auth_revoked("revoked")
    result = subprocess.CompletedProcess(
        args=["codex", "login", "status"],
        returncode=0,
        stdout="Logged in using ChatGPT",
        stderr="",
    )
    state, detail = _interpret_cli_status(spec, result)
    assert state == "logged_out"
    assert detail is not None and "revoked" in detail


def test_run_codex_failfast_on_revoked_stderr(monkeypatch):
    """A live subprocess emitting the revoked marker dies in <~2s, not idle-timeout."""
    monkeypatch.delenv("AGENT_LAB_MOCK_AGENTS", raising=False)
    script = f"import sys, time\nsys.stderr.write({REVOKED_LINE!r})\nsys.stderr.flush()\ntime.sleep(30)\n"
    cmd = [sys.executable, "-c", script]
    import time

    started = time.monotonic()
    with pytest.raises(RuntimeError) as exc_info:
        _run_codex(
            cmd,
            "prompt",
            on_activity=lambda _line: None,
            timeout=60,
            room_turn=True,
        )
    elapsed = time.monotonic() - started
    assert "auth" in str(exc_info.value)
    assert "revoked" in str(exc_info.value)
    assert "/login" in str(exc_info.value)
    assert elapsed < 10, f"fail-fast took {elapsed:.1f}s — should abort immediately"
    # The live failure is recorded for preflight.
    assert codex_auth_revoked_detail() is not None
