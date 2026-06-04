#!/usr/bin/env python3
"""CLI: bootstrap workspace memory files (PROJECT, AGENTS, SHARED_CONTEXT)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap .agent-lab/PROJECT.md, AGENTS.md, SHARED_CONTEXT.md.",
    )
    parser.add_argument("workspace", nargs="?", default=".", help="Workspace root")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing files")
    parser.add_argument("--dry-run", action="store_true", help="Print PROJECT.md only")
    args = parser.parse_args(argv)

    from agent_lab.project_memory import (
        agents_md_path,
        bootstrap_workspace_memory,
        project_md_path,
        shared_context_path,
    )

    root = Path(args.workspace)
    files = bootstrap_workspace_memory(
        root,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        sys.stdout.write(files["project"])
        return 0
    print(f"Wrote {project_md_path(root)} ({len(files['project'])} chars)")
    print(f"Wrote {agents_md_path(root)} ({len(files['agents'])} chars)")
    print(f"Wrote {shared_context_path(root)} ({len(files['shared'])} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
