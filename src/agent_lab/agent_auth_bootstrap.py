"""Startup auth bootstrap — keep Room agents ready across `make dev` restarts.

Runs once per API process after config + dotenv + credentials are loaded.
Does not call LLMs; only syncs stored OAuth profiles and persists API keys.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _append_dotenv_line(key: str, value: str) -> None:
    from agent_lab.app_config import config_dir

    path = config_dir() / ".env"
    prefix = f"{key}="
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if not ln.strip().startswith(prefix)]
    while kept and not kept[-1].strip():
        kept.pop()
    kept.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def persist_cursor_api_key_from_env() -> bool:
    """Mirror CURSOR_API_KEY into credentials.toml + ~/.agent-lab/.env when missing."""
    key = (os.getenv("CURSOR_API_KEY") or "").strip()
    if not key:
        return False
    from agent_lab.credential_store import load_credentials, save_credentials

    data = load_credentials(create_default=False)
    cursor = data.setdefault("cursor", {})
    if not isinstance(cursor, dict):
        cursor = {}
        data["cursor"] = cursor
    if str(cursor.get("primary") or "").strip():
        return False
    cursor["primary"] = key
    cursor.setdefault("primary_label", "메인")
    cursor.setdefault("fallback_label", "서브")
    save_credentials(data)
    _append_dotenv_line("CURSOR_API_KEY", key)
    return True


def persist_tool_bins_from_env() -> list[str]:
    """Ensure GUI-facing ~/.agent-lab/.env has absolute CLI paths when discoverable."""
    from agent_lab.app_config import config_dir

    dotenv_path = config_dir() / ".env"
    existing = dotenv_path.read_text(encoding="utf-8") if dotenv_path.is_file() else ""
    written: list[str] = []
    for key in ("CODEX_BIN", "CLAUDE_BIN", "CURSOR_SDK_BRIDGE_BIN"):
        val = (os.getenv(key) or "").strip()
        if not val or f"{key}=" in existing:
            continue
        _append_dotenv_line(key, val)
        written.append(key)
    return written


def sync_codex_oauth_on_startup() -> dict[str, Any]:
    """Apply captured Codex OAuth primary to live session; drop stale fallback profile."""
    from agent_lab.codex_oauth import (
        _profile_auth_fingerprint,
        apply_profile,
        clear_profile,
        live_auth_path,
        live_login_status,
        profile_exists,
        public_codex_oauth_payload,
    )

    result: dict[str, Any] = {"applied_primary": False, "cleared_fallback": False}
    if profile_exists("primary") and profile_exists("fallback"):
        primary_fp = _profile_auth_fingerprint("primary")
        fallback_fp = _profile_auth_fingerprint("fallback")
        if primary_fp and fallback_fp and primary_fp != fallback_fp:
            clear_profile("fallback")
            result["cleared_fallback"] = True

    live = live_auth_path()
    if profile_exists("primary"):
        primary_fp = _profile_auth_fingerprint("primary")
        live_fp = None
        if live.is_file():
            import hashlib

            live_fp = hashlib.sha256(live.read_bytes()).hexdigest()[:16]
        live_ok, _ = live_login_status()
        if not live_ok or (primary_fp and live_fp and primary_fp != live_fp):
            apply_profile("primary")
            result["applied_primary"] = True
    result["oauth"] = public_codex_oauth_payload()
    return result


def warm_claude_auth_cache() -> dict[str, Any]:
    """Light `claude auth status` — no headless -p probe at startup."""
    from agent_lab import claude_cli

    claude_cli.invalidate_claude_auth_cache()
    ok, detail = claude_cli.claude_auth_logged_in(use_cache=False)
    return {"ok": ok, "detail": detail}


def bootstrap_room_auth_on_startup() -> dict[str, Any]:
    """Idempotent startup hook — call from FastAPI lifespan after env is loaded."""
    if _env_truthy("AGENT_LAB_SKIP_AUTH_BOOTSTRAP"):
        return {"skipped": True}

    from agent_lab.app_logging import write_boot_line
    from agent_lab.runtime_paths import configure_subprocess_path

    configure_subprocess_path()

    summary: dict[str, Any] = {
        "cursor_key_persisted": persist_cursor_api_key_from_env(),
        "tool_bins_persisted": persist_tool_bins_from_env(),
        "codex": sync_codex_oauth_on_startup(),
        "claude": warm_claude_auth_cache(),
    }

    try:
        from agent_lab.credential_store import apply_credentials_to_env

        apply_credentials_to_env()
    except Exception:
        pass

    parts = []
    if summary["cursor_key_persisted"]:
        parts.append("cursor_key→~/.agent-lab")
    if summary["tool_bins_persisted"]:
        parts.append("bins=" + ",".join(summary["tool_bins_persisted"]))
    if summary["codex"].get("applied_primary"):
        parts.append("codex_oauth=synced")
    if summary["codex"].get("cleared_fallback"):
        parts.append("codex_fallback=cleared")
    claude = summary["claude"]
    parts.append(f"claude={'ok' if claude.get('ok') else 'login_required'}")
    write_boot_line("auth bootstrap: " + "; ".join(parts))
    return summary
