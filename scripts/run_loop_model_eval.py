#!/usr/bin/env python3
"""Live/mock loop capability eval — writes `.agent-lab/loop_model_eval.json`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe agent models for Loop readiness and write loop_model_eval.json.",
    )
    parser.add_argument(
        "agents",
        nargs="*",
        help="Agent ids (default: cursor codex claude)",
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Infrastructure probe only (no LLM call)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force AGENT_LAB_MOCK_AGENTS=1 for deterministic mock eval",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Require real agents (clears mock flag if set)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print JSON only; do not write registry file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override registry output path",
    )
    args = parser.parse_args(argv)

    if args.mock:
        import os

        os.environ["AGENT_LAB_MOCK_AGENTS"] = "1"
        os.environ.setdefault("AGENT_LAB_MOCK_STRUCTURED_ENVELOPE", "1")
        os.environ.pop("AGENT_LAB_MOCK_ACT_SCRIPT", None)
    if args.live:
        import os

        os.environ.pop("AGENT_LAB_MOCK_AGENTS", None)

    from agent_lab.loop_probe_eval import run_loop_model_eval

    agent_ids = args.agents or None
    rows = run_loop_model_eval(
        agent_ids,
        static_only=args.static_only,
        write_registry=not args.dry_run,
        registry_path=args.output,
    )
    if args.dry_run:
        sys.stdout.write(json.dumps({"profiles": rows}, indent=2, ensure_ascii=False) + "\n")
    else:
        out = args.output
        if out is None:
            from agent_lab.model_policy import _loop_eval_registry_path

            out = _loop_eval_registry_path()
        print(f"Wrote {len(rows)} profile(s) to {out}")
        for row in rows:
            flags = [
                "tools" if row.get("supports_tools") else "no-tools",
                "inbox" if row.get("supports_inbox_mcp") else "no-inbox",
                "envelope" if row.get("supports_json_envelope") else "no-envelope",
            ]
            err = row.get("eval_error")
            suffix = f" err={err}" if err else ""
            print(f"  {row.get('agent')}:{row.get('model_id')} [{row.get('eval_source')}] {', '.join(flags)}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
