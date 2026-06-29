#!/usr/bin/env python3
"""Manual Tier C Go/No-Go: live Cursor SDK dry-run approved into disposable git."""

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
from scripts.soak.live_execute_spike import (
    format_report_lines,
    run_live_worktree_merge_spike,
)


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
    keep = "--keep-artifacts" in argv
    write_path: Path | None = None
    work_parent: Path | None = None

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
        if arg in ("--json", "--keep-artifacts"):
            i += 1
            continue
        if arg == "--write" and i + 1 < len(argv):
            write_path = Path(argv[i + 1]).expanduser()
            i += 2
            continue
        if arg == "--work-dir" and i + 1 < len(argv):
            work_parent = Path(argv[i + 1]).expanduser()
            i += 2
            continue
        print(f"Unknown argument: {arg}", file=sys.stderr)
        return 1

    _load_env()
    report = run_live_worktree_merge_spike(
        work_parent=work_parent,
        cleanup=not keep and work_parent is None,
    )

    if write_path:
        write_path.parent.mkdir(parents=True, exist_ok=True)
        write_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for line in format_report_lines(report):
            print(line)

    status = report.get("status")
    if status == "go":
        return 0
    if status == "skipped":
        return 3
    return 2


_USAGE = """Usage: live_cursor_worktree_merge_run.py (requires AGENT_LAB_RUN_LIVE=1)

Runs one real Cursor dry-run in a disposable git worktree, then approves and
merges it into the disposable repo base branch. Never targets agent-lab main.

Environment:
  CURSOR_API_KEY          Required (also loaded from ~/.agent-lab/.env or repo .env)
  CURSOR_SDK_BRIDGE_BIN   Optional auto-launch bridge
  AGENT_LAB_SKIP_LIVE=1   Skip without calling Cursor

Options:
  --json              Machine-readable report on stdout
  --write PATH        Save report JSON (no secrets)
  --work-dir PATH     Reuse parent dir (repo/ + session/); implies --keep-artifacts
  --keep-artifacts    Do not delete temp work dir (debug)

Exit codes: 0=go, 2=no_go, 3=skipped, 1=usage/guard
"""


if __name__ == "__main__":
    raise SystemExit(main())
