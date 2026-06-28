#!/usr/bin/env python3
"""Fail when code imports legacy ``agent_lab.mission_*`` paths."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (ROOT / "src" / "agent_lab", ROOT / "app", ROOT / "tests", ROOT / "scripts")

LEGACY_RE = re.compile(
    r"\b(?:from|import)\s+agent_lab\.mission_[a-z_]+|\bagent_lab\.mission_[a-z_]+\b"
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
                if "mission_*" in line and "agent_lab" not in line:
                    continue
                if LEGACY_RE.search(line):
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
        print(f"Legacy mission_* imports: {len(hits)}")
        for row in hits:
            print(f"  {row['path']}:{row['line']}: {row['text']}")
    else:
        print("Legacy mission_* imports: 0 (OK)")

    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
