"""User config for packaged Agent Lab (~/.agent-lab/config.toml).

Configuration precedence (later steps do not override explicit env vars):
  1. ``~/.agent-lab/.env`` — secrets and absolute tool paths (CODEX_BIN, …)
  2. ``~/.agent-lab/config.toml`` — paths.sessions, paths.agent_lab, api.port, logging.dir
  3. Repo ``.env`` / ``DOTENV_PATH`` — developer overrides (loaded in app.server.main)
  4. ``runtime_paths.configure_subprocess_path()`` — auto-fill PATH and bridge bin when unset

``resolve_sessions_dir()``: ``AGENT_LAB_SESSIONS_DIR`` env → config ``paths.sessions`` →
``paths.agent_lab``/sessions → ~/Projects/agent-lab/sessions → repo ``sessions/``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None  # type: ignore[assignment,misc]

DEFAULT_CONFIG_DIR = Path.home() / ".agent-lab"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"
DEFAULT_LOG_DIR = Path.home() / "Library" / "Logs" / "Agent Lab"


def config_dir() -> Path:
    raw = os.getenv("AGENT_LAB_CONFIG_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_CONFIG_DIR.resolve()


def config_path() -> Path:
    raw = os.getenv("AGENT_LAB_CONFIG_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return config_dir() / "config.toml"


def _expand_path(raw: str | None) -> Path | None:
    if not raw or not str(raw).strip():
        return None
    path = Path(str(raw).strip()).expanduser()
    if path.is_dir() or path.is_file():
        return path.resolve()
    if path.expanduser().exists():
        return path.expanduser().resolve()
    return None


def default_config_dict() -> dict[str, Any]:
    home = Path.home()
    paths: dict[str, str] = {}
    for candidate, key in (
        (home / "Projects" / "agent-lab", "agent_lab"),
        (home / "Desktop" / "pipeline", "quant_pipeline"),
        (home / "Projects" / "quant-pipeline", "quant_pipeline"),
        (home / "Projects" / "quant-agentic-trading", "agentic_trading"),
    ):
        if candidate.is_dir() and key not in paths:
            paths[key] = str(candidate.resolve())
    return {
        "paths": paths,
        "api": {"port": 8765},
        "logging": {"dir": str(DEFAULT_LOG_DIR)},
    }


def write_default_config(path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        return target
    data = default_config_dict()
    lines = [
        "# Agent Lab user config — edit paths for your machine.",
        "",
        "[paths]",
    ]
    if data["paths"].get("quant_pipeline"):
        lines.append(f'# quant_pipeline = "{data["paths"]["quant_pipeline"]}"  # optional extension')
    if data["paths"].get("agentic_trading"):
        lines.append(f'# agentic_trading = "{data["paths"]["agentic_trading"]}"  # optional extension')
    if data["paths"].get("agent_lab"):
        lines.append(f'# agent_lab = "{data["paths"]["agent_lab"]}"')
    lines.extend(
        [
            "",
            "[api]",
            "port = 8765",
            "",
            "[logging]",
            f'dir = "{data["logging"]["dir"]}"',
            "",
        ]
    )
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def load_config(*, create_default: bool = True) -> dict[str, Any]:
    path = config_path()
    if not path.is_file():
        if create_default:
            write_default_config(path)
        if not path.is_file():
            return default_config_dict()
    if tomllib is None:
        return default_config_dict()
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_config_dict()
    if not isinstance(parsed, dict):
        return default_config_dict()
    return parsed


def resolve_sessions_dir(cfg: dict[str, Any] | None = None) -> Path:
    """Same sessions root for tauri-dev, tauri build, and CLI."""
    raw = os.getenv("AGENT_LAB_SESSIONS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()

    data = cfg if cfg is not None else load_config(create_default=False)
    paths = data.get("paths") if isinstance(data.get("paths"), dict) else {}
    if isinstance(paths, dict):
        explicit = _expand_path(str(paths.get("sessions") or ""))
        if explicit is not None:
            return explicit
        lab = _expand_path(str(paths.get("agent_lab") or ""))
        if lab is not None:
            return (lab / "sessions").resolve()

    home = Path.home()
    home_repo = home / "Projects" / "agent-lab" / "sessions"
    if home_repo.is_dir():
        return home_repo.resolve()

    from agent_lab.workspace_roots import project_root

    return (project_root() / "sessions").resolve()


def apply_config_env(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply config.toml values to os.environ when not already set."""
    data = cfg if cfg is not None else load_config()
    paths = data.get("paths") if isinstance(data.get("paths"), dict) else {}
    if isinstance(paths, dict):
        if not os.getenv("QUANT_PIPELINE_ROOT"):
            qp = _expand_path(str(paths.get("quant_pipeline") or ""))
            if qp is not None:
                os.environ["QUANT_PIPELINE_ROOT"] = str(qp)
        if not os.getenv("AGENTIC_QUANT_PIPELINE_SRC"):
            at = _expand_path(str(paths.get("agentic_trading") or ""))
            if at is not None:
                src = at / "src"
                if src.is_dir():
                    os.environ["AGENTIC_QUANT_PIPELINE_SRC"] = str(src.resolve())
        if not os.getenv("AGENT_LAB_ROOT"):
            lab = _expand_path(str(paths.get("agent_lab") or ""))
            if lab is not None:
                os.environ["AGENT_LAB_ROOT"] = str(lab)
        runtime = (os.getenv("AGENT_LAB_ROOT") or "").strip()
        if runtime:
            from agent_lab.workspace_roots import is_bundled_app_runtime

            if is_bundled_app_runtime(runtime) and not os.getenv("AGENT_LAB_DEV_ROOT"):
                dev = _expand_path(str(paths.get("agent_lab") or ""))
                if dev is None:
                    home_lab = Path.home() / "Projects" / "agent-lab"
                    if home_lab.is_dir():
                        dev = home_lab.resolve()
                if dev is not None:
                    os.environ["AGENT_LAB_DEV_ROOT"] = str(dev)
        if not os.getenv("AGENT_LAB_SESSIONS_DIR"):
            sessions = resolve_sessions_dir(data)
            os.environ["AGENT_LAB_SESSIONS_DIR"] = str(sessions)
    api = data.get("api") if isinstance(data.get("api"), dict) else {}
    if isinstance(api, dict) and api.get("port") and not os.getenv("AGENT_LAB_API_PORT"):
        os.environ["AGENT_LAB_API_PORT"] = str(int(api["port"]))
    logging_cfg = data.get("logging") if isinstance(data.get("logging"), dict) else {}
    if isinstance(logging_cfg, dict) and logging_cfg.get("dir") and not os.getenv("AGENT_LAB_LOG_DIR"):
        raw_log = str(logging_cfg["dir"]).strip()
        if raw_log:
            os.environ["AGENT_LAB_LOG_DIR"] = str(Path(raw_log).expanduser().resolve())
    from agent_lab.runtime_paths import configure_subprocess_path

    configure_subprocess_path()
    return data


def log_dir() -> Path:
    raw = os.getenv("AGENT_LAB_LOG_DIR", "").strip()
    if raw:
        path = Path(raw).expanduser()
    else:
        cfg = load_config(create_default=False)
        logging_cfg = cfg.get("logging") if isinstance(cfg.get("logging"), dict) else {}
        raw_dir = logging_cfg.get("dir") if isinstance(logging_cfg, dict) else None
        path = Path(str(raw_dir)).expanduser() if raw_dir else DEFAULT_LOG_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()
