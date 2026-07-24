"""CLI: report line, word, and character counts for a text file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def count_stats(text: str) -> tuple[int, int, int]:
    """Return (lines, words, characters).

    - lines: ``len(text.splitlines())`` — empty file → 0
    - words: whitespace-separated via ``text.split()``
    - characters: ``len(text)`` including newlines
    """
    lines = len(text.splitlines())
    words = len(text.split())
    characters = len(text)
    return lines, words, characters


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="text_stats",
        description="Count lines, words, and characters in a text file",
    )
    parser.add_argument("path", type=Path, help="Path to a text file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        path: Path = args.path
        if not path.is_file():
            print(f"Error: file not found: {path}", file=sys.stderr)
            return 1
        text = path.read_text(encoding="utf-8")
        lines, words, characters = count_stats(text)
        print(f"Lines: {lines}")
        print(f"Words: {words}")
        print(f"Characters: {characters}")
        return 0
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except SystemExit:
        raise


if __name__ == "__main__":
    sys.exit(main())
