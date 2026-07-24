from __future__ import annotations

"""line_stats CLI — count lines and characters across text files."""

import argparse
import sys
from pathlib import Path


def count_file(path: Path) -> tuple[int, int]:
    """Return (line_count, char_count) for a single file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    return len(lines), len(text)


def run(paths: list[Path]) -> None:
    if not paths:
        print("No files specified.", file=sys.stderr)
        sys.exit(1)

    total_lines = 0
    total_chars = 0
    missing = []

    rows: list[tuple[str, int, int]] = []
    for p in paths:
        if not p.is_file():
            missing.append(str(p))
            continue
        lines, chars = count_file(p)
        total_lines += lines
        total_chars += chars
        rows.append((p.name, lines, chars))

    if missing:
        for m in missing:
            print(f"warning: not found: {m}", file=sys.stderr)

    if not rows:
        print("No valid files found.", file=sys.stderr)
        sys.exit(1)

    name_w = max(len(r[0]) for r in rows)
    name_w = max(name_w, 4)  # at least "File"

    header = f"{'File':<{name_w}}  {'Lines':>7}  {'Chars':>10}"
    sep = "-" * len(header)
    print(header)
    print(sep)
    for name, lines, chars in rows:
        print(f"{name:<{name_w}}  {lines:>7}  {chars:>10}")
    print(sep)
    print(f"{'TOTAL':<{name_w}}  {total_lines:>7}  {total_chars:>10}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="line_stats",
        description="Summarise line and character counts for one or more text files.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        metavar="FILE",
        help="Text file(s) to analyse",
    )
    args = parser.parse_args(argv)
    run([Path(f) for f in args.files])


if __name__ == "__main__":
    main()
