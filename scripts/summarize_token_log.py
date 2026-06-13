#!/usr/bin/env python3
"""Summarize recent Trading Mission rows from tasks/.token_log.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize tasks/.token_log.jsonl")
    parser.add_argument("--lines", type=int, default=20, help="Last N records")
    parser.add_argument(
        "--pipeline",
        type=Path,
        default=None,
        help="QUANT_PIPELINE_ROOT override",
    )
    args = parser.parse_args()

    from agent_lab.trading_mission.telemetry import _token_log_path

    import os

    if args.pipeline:
        os.environ["QUANT_PIPELINE_ROOT"] = str(args.pipeline.expanduser().resolve())

    path = _token_log_path()
    if path is None or not path.is_file():
        print(json.dumps({"ok": False, "reason": "token log path missing"}, ensure_ascii=False))
        return 1

    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    tail = rows[-max(1, args.lines) :]
    summary = {
        "ok": True,
        "path": str(path),
        "count": len(tail),
        "records": tail,
        "totals": {
            "input_tokens_est": sum(int(r.get("input_tokens_est") or 0) for r in tail),
            "output_tokens_est": sum(int(r.get("output_tokens_est") or 0) for r in tail),
            "agent_invocations": sum(int(r.get("agent_invocations") or 0) for r in tail),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
