"""Pure syntax scan for merge gate — no execution dict / env (Track 2.0b seam).

Future PyO3 target: :func:`scan_python_syntax` only; path resolution stays in
``syntax_gate.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def scan_python_syntax(paths: list[Path], *, root: Path | None = None) -> tuple[str, int] | None:
    """Return the first ``(display_path, lineno)`` whose source fails to compile.

    Files are scanned in the given order (``changed_python_files`` already sorts).
    Missing or unreadable files are skipped. Returns None when every readable file parses.
    """
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            compile(source, str(path), "exec")
        except SyntaxError as exc:
            display = path
            if root is not None:
                try:
                    display = path.relative_to(root)
                except ValueError:
                    display = path
            return (str(display), exc.lineno or 0)
        except ValueError:
            continue
    return None


def merge_result_for_syntax_scan(
    paths: list[Path],
    hit: tuple[str, int] | None,
) -> dict[str, Any]:
    """Build the ``{id, ok, detail}`` merge-check payload from a scan outcome."""
    if not paths:
        return {"id": "syntax_gate", "ok": True, "detail": "no changed .py"}
    if hit is None:
        return {"id": "syntax_gate", "ok": True, "detail": f"{len(paths)} .py ok"}
    file, line = hit
    return {"id": "syntax_gate", "ok": False, "detail": f"{file}:{line}"}
