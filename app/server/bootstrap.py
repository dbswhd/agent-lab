"""One-shot environment bootstrap for the Agent Lab API (no import-time side effects)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from agent_lab.app_config import apply_config_env
from agent_lab.credential_store import apply_credentials_to_env

_BOOTSTRAPPED = False


def project_root() -> Path:
    return Path(os.getenv("AGENT_LAB_ROOT", Path(__file__).resolve().parents[2]))


def bootstrap_environment(*, root: Path | None = None) -> None:
    """Apply config, dotenv, credentials, and refresh SESSIONS_DIR. Idempotent."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED or os.getenv("AGENT_LAB_BOOTSTRAPPED") == "1":
        return

    repo_root = root or project_root()
    home = Path.home()

    apply_config_env()

    for env_file in (
        Path(os.getenv("DOTENV_PATH", "")),
        repo_root / ".env",
        home / "Projects/agent-lab/.env",
        home / ".agent-lab/.env",
    ):
        if env_file.is_file():
            load_dotenv(env_file)

    apply_credentials_to_env()

    from agent_lab.session.paths import refresh_sessions_dir

    refresh_sessions_dir()

    os.environ["AGENT_LAB_BOOTSTRAPPED"] = "1"
    _BOOTSTRAPPED = True


def reset_bootstrap_state_for_tests() -> None:
    """Test helper — allow bootstrap_environment() to run again."""
    global _BOOTSTRAPPED
    _BOOTSTRAPPED = False
    os.environ.pop("AGENT_LAB_BOOTSTRAPPED", None)
