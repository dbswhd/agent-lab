"""Bootstrap must apply ~/.agent-lab model prefs over repo .env defaults."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.server.bootstrap import bootstrap_environment, reset_bootstrap_state_for_tests


@pytest.fixture(autouse=True)
def _reset_bootstrap() -> None:
    reset_bootstrap_state_for_tests()
    os.environ.pop("AGENT_LAB_BOOTSTRAPPED", None)
    yield
    reset_bootstrap_state_for_tests()


def test_user_model_prefs_override_repo_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text(
        "CODEX_MODEL=gpt-5.5\nCLAUDE_MODEL=claude-sonnet-4-6\n",
        encoding="utf-8",
    )
    user_cfg = tmp_path / "user-lab"
    user_cfg.mkdir()
    (user_cfg / ".env").write_text(
        "CODEX_MODEL=gpt-5.3-codex\nCLAUDE_MODEL=opus\nCLAUDE_REASONING_EFFORT=medium\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AGENT_LAB_ROOT", str(repo))
    monkeypatch.setenv("AGENT_LAB_CONFIG_DIR", str(user_cfg))
    monkeypatch.delenv("DOTENV_PATH", raising=False)

    bootstrap_environment(root=repo)

    assert os.getenv("CODEX_MODEL") == "gpt-5.3-codex"
    assert os.getenv("CLAUDE_MODEL") == "opus"
    assert os.getenv("CLAUDE_REASONING_EFFORT") == "medium"
