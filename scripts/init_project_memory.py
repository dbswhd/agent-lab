#!/usr/bin/env python3
"""CLI: bootstrap `.agent-lab/PROJECT.md` for a workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap .agent-lab/PROJECT.md from workspace heuristics.",
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        default=".",
        help="Workspace root (default: cwd)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing PROJECT.md",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print markdown without writing",
    )
    args = parser.parse_args(argv)

    from agent_lab.project_memory import bootstrap_project_md, project_md_path

    root = Path(args.workspace)
    text = bootstrap_project_md(
        root,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        sys.stdout.write(text)
        return 0
    path = project_md_path(root)
    print(f"Wrote {path} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
