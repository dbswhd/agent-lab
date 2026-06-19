#!/usr/bin/env python3
"""Report agent_lab modules with zero imports from production code paths."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_lab"
SCAN_DIRS = (ROOT / "src", ROOT / "app", ROOT / "tests", ROOT / "scripts")
IMPORT_RE = re.compile(
    r"(?:from\s+agent_lab\.([a-zA-Z0-9_]+)"
    r"|import\s+agent_lab\.([a-zA-Z0-9_]+)"
    r"|from\s+agent_lab\s+import\s+([a-zA-Z0-9_,\s]+))"
)


def _extract_modules(line: str) -> list[str]:
    found: list[str] = []
    for m in IMPORT_RE.finditer(line):
        dotted, direct, bulk = m.group(1), m.group(2), m.group(3)
        if dotted:
            found.append(dotted.split(".")[0])
        if direct:
            found.append(direct.split(".")[0])
        if bulk:
            for part in bulk.split(","):
                name = part.strip().split(" as ")[0].strip()
                if name:
                    found.append(name)
    return found


def module_names() -> list[str]:
    names: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(SRC)
        if rel.parts[0] in {"agents", "runtime", "gateway", "extensions"}:
            continue
        mod = ".".join(rel.with_suffix("").parts)
        names.append(mod.replace(".", "_") if "/" not in str(rel) else str(rel.with_suffix("")).replace("/", "."))
    # Top-level modules only (flat + one-level packages we care about for freeze)
    flat: list[str] = []
    for path in sorted(SRC.glob("*.py")):
        if path.name != "__init__.py":
            flat.append(path.stem)
    return sorted(set(flat))


def import_refs() -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {}
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "archive/" in str(path):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                for root in _extract_modules(line):
                    refs.setdefault(root, set()).add(str(path.relative_to(ROOT)))
    return refs


def main() -> int:
    mods = module_names()
    refs = import_refs()
    unused = [m for m in mods if m not in refs and m != "__main__"]
    print(f"Scanned {len(mods)} top-level agent_lab modules")
    print(f"Import roots referenced: {len(refs)}")
    if unused:
        print("\nNo imports from src/app/tests/scripts:")
        for name in unused:
            print(f"  - {name}")
    else:
        print("\nAll top-level modules are referenced (archive candidates: 0)")
    print("\nNote: examples/ and archive/ are excluded. Transitive-only deps still count as used.")
    return 0 if not unused else 1


if __name__ == "__main__":
    sys.exit(main())
