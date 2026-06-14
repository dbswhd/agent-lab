#!/usr/bin/env python3
"""Live soak: launchd daemon + tunnel mission-wake (Tier E)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

from agent_lab.app_config import apply_config_env

_USAGE = """Usage: live_tunnel_launchd_soak.py (requires AGENT_LAB_RUN_LIVE=1)

Options:
  --write PATH          Write JSON report
  --api-base URL        Default http://127.0.0.1:8765 or AGENT_LAB_SOAK_API_BASE
  --tunnel-wake URL     Public tunnel base or full .../api/hooks/mission-wake
  --require-launchd     Fail when com.agentlab.serve-daemon is not loaded
  --json                Print report JSON to stdout

Env:
  AGENT_LAB_SCHEDULER_HOOK_TOKEN   Auth for mission-wake (recommended)
  AGENT_LAB_TUNNEL_WAKE_URL        cloudflared/ngrok public URL
  AGENT_LAB_SOAK_SKIP_LAUNCHD=1    Skip launchctl check
"""


def _load_env() -> None:
    apply_config_env()
    home_env = Path.home() / ".agent-lab" / ".env"
    if home_env.is_file():
        load_dotenv(home_env, override=False)
    repo_env = _ROOT / ".env"
    if repo_env.is_file():
        load_dotenv(repo_env, override=False)


def main() -> int:
    argv = sys.argv[1:]
    as_json = "--json" in argv
    require_launchd = "--require-launchd" in argv
    skip_launchd = os.getenv("AGENT_LAB_SOAK_SKIP_LAUNCHD", "").strip() in {"1", "true", "yes"}
    write_path: Path | None = None
    api_base: str | None = None
    tunnel_wake: str | None = None

    if "-h" in argv or "--help" in argv:
        print(_USAGE, file=sys.stderr)
        return 0

    if os.getenv("AGENT_LAB_RUN_LIVE", "").strip() not in {"1", "true", "yes"}:
        print(
            "Refusing to run without AGENT_LAB_RUN_LIVE=1 (safety guard).",
            file=sys.stderr,
        )
        print(_USAGE, file=sys.stderr)
        return 1

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--json", "--require-launchd"):
            i += 1
            continue
        if arg == "--write" and i + 1 < len(argv):
            write_path = Path(argv[i + 1]).expanduser()
            i += 2
            continue
        if arg == "--api-base" and i + 1 < len(argv):
            api_base = argv[i + 1]
            i += 2
            continue
        if arg == "--tunnel-wake" and i + 1 < len(argv):
            tunnel_wake = argv[i + 1]
            i += 2
            continue
        print(f"Unknown argument: {arg}", file=sys.stderr)
        return 1

    _load_env()
    from agent_lab.live_tunnel_launchd_soak import (
        format_tunnel_soak_lines,
        run_live_tunnel_launchd_soak,
    )

    report = run_live_tunnel_launchd_soak(
        api_base=api_base,
        tunnel_wake_url=tunnel_wake,
        require_launchd=require_launchd,
        skip_launchd=skip_launchd,
    )

    if write_path:
        write_path.parent.mkdir(parents=True, exist_ok=True)
        write_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for line in format_tunnel_soak_lines(report):
            print(line)

    status = str(report.get("status") or "no_go")
    if status == "go":
        return 0
    if status == "skipped":
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
