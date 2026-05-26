#!/usr/bin/env python3
"""Validate plan.md chat.jsonl#L refs for a room session folder."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from agent_lab.plan_refs import (  # noqa: E402
    validate_plan_ref_meaning,
    validate_plan_refs,
)


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--semantic"]
    semantic = "--semantic" in sys.argv[1:]
    if len(args) != 1:
        print(
            f"Usage: {sys.argv[0]} [--semantic] <session-folder>",
            file=sys.stderr,
        )
        return 2
    folder = Path(args[0]).expanduser().resolve()
    if not folder.is_dir():
        print(f"Not a directory: {folder}", file=sys.stderr)
        return 2
    result = validate_plan_refs(folder)
    print(result.summary())
    if result.refs:
        print(f"  refs: {result.refs}")
    if result.has_unclear:
        print("  note: contains (ref: 불명확)")
    exit_code = 0 if result.valid else 1
    if semantic:
        meaning = validate_plan_ref_meaning(folder)
        print(meaning.summary())
        for w in meaning.warnings:
            print(
                f"  plan L{w.plan_line}: shared={w.shared_count} "
                f"score={w.overlap_score} refs={w.refs}"
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
