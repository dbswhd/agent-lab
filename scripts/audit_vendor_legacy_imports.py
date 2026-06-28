#!/usr/bin/env python3
"""Fail when code imports legacy root vendor paths (cursor_*, codex_*, claude_*, bridge_registry, bridge_stdout_parser, local_provider)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (ROOT / "src" / "agent_lab", ROOT / "app", ROOT / "tests", ROOT / "scripts")

LEGACY_RES = (
    re.compile(r"\b(?:from|import)\s+agent_lab\.cursor_[a-z_]+"),
    re.compile(r"\bagent_lab\.cursor_[a-z_]+\b"),
    re.compile(r"\b(?:from|import)\s+agent_lab\.codex_[a-z_]+"),
    re.compile(r"\bagent_lab\.codex_[a-z_]+\b"),
    re.compile(r"\b(?:from|import)\s+agent_lab\.claude_[a-z_]+"),
    re.compile(r"\bagent_lab\.claude_[a-z_]+\b"),
    re.compile(r"\b(?:from|import)\s+agent_lab\.bridge_registry\b"),
    re.compile(r"\bagent_lab\.bridge_registry\b"),
    re.compile(r"\b(?:from|import)\s+agent_lab\.bridge_stdout_parser\b"),
    re.compile(r"\bagent_lab\.bridge_stdout_parser\b"),
    re.compile(r"\b(?:from|import)\s+agent_lab\.local_provider\b"),
    re.compile(r"\bagent_lab\.local_provider\b"),
)


def collect_violations() -> list[dict[str, str | int]]:
    hits: list[dict[str, str | int]] = []
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if path.name.startswith("migrate_") and "package" in path.name:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if any(rx.search(line) for rx in LEGACY_RES):
                    hits.append(
                        {
                            "path": str(path.relative_to(ROOT)),
                            "line": lineno,
                            "text": line.strip(),
                        }
                    )
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    hits = collect_violations()
    if args.json:
        print(json.dumps({"violations": hits, "count": len(hits)}, indent=2))
    elif hits:
        print(f"Legacy vendor root imports: {len(hits)}")
        for row in hits:
            print(f"  {row['path']}:{row['line']}: {row['text']}")
    else:
        print("Legacy vendor root imports: 0 (OK)")

    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
