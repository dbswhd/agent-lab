"""File logging for packaged Agent Lab API."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def setup_app_logging(*, log_dir: Path | None = None) -> Path:
    global _CONFIGURED
    from agent_lab.app_config import log_dir as resolve_log_dir

    directory = log_dir or resolve_log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "agent-lab-api.log"

    if _CONFIGURED:
        return log_path

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    _CONFIGURED = True
    logging.getLogger("agent_lab.bootstrap").info(
        "logging initialized path=%s python=%s",
        log_path,
        sys.executable,
    )
    return log_path


def write_boot_line(message: str, *, log_dir: Path | None = None) -> None:
    from agent_lab.app_config import log_dir as resolve_log_dir

    directory = log_dir or resolve_log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    boot = directory / "agent-lab-boot.log"
    stamp = datetime.now(timezone.utc).isoformat()
    with boot.open("a", encoding="utf-8") as f:
        f.write(f"{stamp} {message}\n")
