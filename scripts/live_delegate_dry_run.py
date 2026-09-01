#!/usr/bin/env python3
"""C5 Go/No-Go: live delegate dry-run (worktree + external handoff attach)."""

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
from scripts.soak.live_delegate_spike import format_report_lines, run_live_delegate_spike

_USAGE = """Usage: live_delegate_dry_run.py

Modes:
  mock (default)  — shell delegate in temp tools.yaml; no Codex call
  codex           — set AGENT_LAB_RUN_LIVE=1 or DELEGATE_SPIKE_MODE=codex

Requires:
  AGENT_LAB_EXTERNAL_TOOLS=1 (set by script)
  ~/.agent-lab/tools.yaml with external:codex-delegate (codex mode)
  Session allowlist is patched inside the spike

Options:
  --json
  --keep-artifacts
  --work-dir PATH
  --write PATH
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
    keep = "--keep-artifacts" in argv
    write_path: Path | None = None
    work_parent: Path | None = None

    if "-h" in argv or "--help" in argv:
        print(_USAGE, file=sys.stderr)
        return 0

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
    os.environ.setdefault("AGENT_LAB_EXTERNAL_TOOLS", "1")

    report = run_live_delegate_spike(
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

    return 0 if report.get("status") == "go" else 1


if __name__ == "__main__":
    raise SystemExit(main())
