from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def sum_column(path: str | Path, column: str) -> float:
    """Return the sum of *column* in the CSV at *path*.

    Raises:
        SystemExit: with a human-readable message for all expected error cases
            (empty file, missing header row, unknown column, non-numeric value).
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")

    if not text.strip():
        sys.exit(f"Error: '{p}' is empty.")

    reader = csv.DictReader(text.splitlines())

    if reader.fieldnames is None:
        sys.exit(f"Error: '{p}' has no header row.")

    if column not in reader.fieldnames:
        available = ", ".join(reader.fieldnames)
        sys.exit(f"Error: column '{column}' not found in '{p}'.\nAvailable columns: {available}")

    total = 0.0
    for i, row in enumerate(reader, start=2):  # row 1 = header
        raw = row[column]
        if raw is None or raw.strip() == "":
            sys.exit(f"Error: empty value in column '{column}' at row {i}.")
        try:
            total += float(raw)
        except ValueError:
            sys.exit(f"Error: non-numeric value '{raw}' in column '{column}' at row {i}.")

    return total


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Sum a numeric column in a CSV file.")
    parser.add_argument("file", help="Path to the CSV file")
    parser.add_argument("--column", required=True, help="Column name to sum")
    args = parser.parse_args(argv)

    result = sum_column(args.file, args.column)
    print(result)


if __name__ == "__main__":
    main()
