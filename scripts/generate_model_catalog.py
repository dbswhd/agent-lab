#!/usr/bin/env python3
"""Generate ``model_catalog.json`` from bundled seed, Codex OAuth discovery, and overrides."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_lab.agent import catalog_generate as cg  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when generated catalog differs from committed model_catalog.json",
    )
    parser.add_argument(
        "--no-discover",
        action="store_true",
        help="Skip Codex OAuth discovery (apply overrides to bundled seed only)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=cg.CATALOG_PATH,
        help="Output path (default: src/agent_lab/agent/model_catalog.json)",
    )
    args = parser.parse_args()

    seed = cg._read_json(cg.CATALOG_PATH)
    generated, sources, detail = cg.generate_catalog(seed=seed, discover_codex=not args.no_discover)
    if detail:
        print(f"Codex discovery skipped: {detail}", file=sys.stderr)

    if args.check:
        committed = cg._read_json(cg.CATALOG_PATH)
        if not cg.catalogs_equivalent(generated, committed):
            print("model catalog is out of date — run: make generate-model-catalog", file=sys.stderr)
            return 1
        print("model catalog OK")
        return 0

    cg.write_catalog(generated, args.out)
    provider_count = len(generated.get("providers") or {})
    print(f"Wrote {args.out} ({provider_count} providers, sources={sources})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
