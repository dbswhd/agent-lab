"""Lightweight SESSIONS_DIR constant — no heavy dependencies.

Importable without langgraph/langchain_core so test patching works.
"""

from __future__ import annotations

import os
from pathlib import Path

from agent_lab.app_config import apply_config_env, resolve_sessions_dir

apply_config_env()
SESSIONS_DIR = Path(os.getenv("AGENT_LAB_SESSIONS_DIR", resolve_sessions_dir()))
