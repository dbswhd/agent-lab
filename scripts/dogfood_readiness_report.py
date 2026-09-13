#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
# ─── How to run ───
# make dogfood-readiness-report MANIFEST=path/to/manifest.json
"""Write a concise dogfood readiness JSON/Markdown packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dogfood_readiness_manifest import load_manifest
from dogfood_readiness_packet import build_readiness_packet, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    packet = build_readiness_packet(load_manifest(args.manifest))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "dogfood-readiness.json"
    markdown_path = args.out_dir / "dogfood-readiness.md"
    json_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(packet), encoding="utf-8")
    print(f"readiness={packet['readiness']}")
    print(f"json={json_path}")
    print(f"markdown={markdown_path}")
    return 1 if args.check and packet["readiness"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
