#!/usr/bin/env python3
"""Offline session quality KPI report (Phase H4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from agent_lab.session.score import score_session  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv[1:]
    if len(args) != 1:
        print(
            f"Usage: {sys.argv[0]} [--json] <session-folder>",
            file=sys.stderr,
        )
        return 1
    folder = Path(args[0]).expanduser().resolve()
    if not folder.is_dir():
        print(f"Not a directory: {folder}", file=sys.stderr)
        return 1
    report = score_session(folder)
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for line in report.get("summary_lines") or []:
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
